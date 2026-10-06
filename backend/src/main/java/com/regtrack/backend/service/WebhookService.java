package com.regtrack.backend.service;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import com.regtrack.backend.dto.WebhookDtos.ChangeEventResponse;
import com.regtrack.backend.dto.WebhookDtos.WebhookAckResponse;
import com.regtrack.backend.exception.BadRequestException;
import com.regtrack.backend.model.ChangeEvent;
import com.regtrack.backend.model.ChangeStatus;
import com.regtrack.backend.model.Regulation;
import com.regtrack.backend.model.RegulationSource;
import com.regtrack.backend.model.RegulationVersion;
import com.regtrack.backend.repository.ChangeEventRepository;
import com.regtrack.backend.repository.RegulationRepository;
import com.regtrack.backend.repository.RegulationSourceRepository;
import com.regtrack.backend.repository.RegulationVersionRepository;
import com.regtrack.backend.security.WebhookHmacFilter;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.net.URI;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

/**
 * Receives change events from the monitoring layer (ChangeDetection.io via n8n/Firecrawl),
 * persists the event and, when the payload carries the new content, versions the document.
 * AI analysis (Phase 4) and relevance scoring consume the resulting change events.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class WebhookService {

    private final ObjectMapper objectMapper;
    private final RegulationSourceRepository sourceRepository;
    private final RegulationRepository regulationRepository;
    private final RegulationVersionRepository versionRepository;
    private final ChangeEventRepository eventRepository;
    private final AuditService auditService;
    private final ExtractionService extractionService;

    @Transactional
    public WebhookAckResponse receive(String rawBody, String ipAddress) {
        JsonNode payload;
        try {
            payload = objectMapper.readTree(rawBody);
        } catch (Exception ex) {
            throw new BadRequestException("Webhook payload must be valid JSON");
        }
        if (payload == null || !payload.isObject()) {
            throw new BadRequestException("Webhook payload must be a JSON object");
        }

        String url = firstText(payload, "url", "page_url", "link");
        if (url == null || url.isBlank()) {
            throw new BadRequestException("Missing required field: url");
        }
        url = url.trim();

        RegulationSource source = resolveSource(payload, url);
        Regulation regulation = null;
        Long oldVersionId = null;
        Long newVersionId = null;

        if (source != null) {
            String title = firstText(payload, "title", "name", "subject");
            regulation = regulationRepository.findByUrl(url).orElse(null);
            if (regulation == null) {
                regulation = regulationRepository.save(Regulation.builder()
                        .sourceId(source.getId())
                        .title(title != null && !title.isBlank() ? title.trim() : defaultTitle(url))
                        .url(url)
                        .category(firstText(payload, "category", "type"))
                        .build());
            } else if (title != null && !title.isBlank() && !title.trim().equals(regulation.getTitle())) {
                regulation.setTitle(title.trim());
                regulation = regulationRepository.save(regulation);
            }

            String content = firstText(payload, "content", "snapshot", "text", "markdown", "md", "body");
            if (content == null || content.isBlank()) {
                try {
                    var extracted = extractionService.extract(url, "AUTO");
                    if (extracted != null && Boolean.TRUE.equals(extracted.success()) && extracted.markdown() != null) {
                        content = extracted.markdown();
                    }
                } catch (Exception e) {
                    log.warn("Auto-extraction fallback failed for webhook URL {}: {}", url, e.getMessage());
                }
            }

            if (content != null && !content.isBlank()) {
                Optional<RegulationVersion> current =
                        versionRepository.findFirstByRegulationIdAndCurrentTrue(regulation.getId());
                String hash = WebhookHmacFilter.sha256Hex(content);

                if (current.isPresent()) {
                    oldVersionId = current.get().getId();
                    if (!hash.equals(current.get().getContentHash())) {
                        current.get().setCurrent(false);
                        versionRepository.save(current.get());
                        newVersionId = saveVersion(regulation, current.get().getVersionNo() + 1, content, hash, url);
                    }
                } else {
                    newVersionId = saveVersion(regulation, 1, content, hash, url);
                }
            }
        }

        ChangeEvent event = eventRepository.save(ChangeEvent.builder()
                .sourceId(source != null ? source.getId() : null)
                .regulationId(regulation != null ? regulation.getId() : null)
                .oldVersionId(oldVersionId)
                .newVersionId(newVersionId)
                .status(ChangeStatus.RECEIVED)
                .payloadUrl(url)
                .payloadJson(rawBody)
                .receivedAt(LocalDateTime.now())
                .build());

        auditService.record("webhook-system", "SYSTEM", "WEBHOOK_RECEIVED", "ChangeEvent", event.getId(),
                "Change detected: " + url, ipAddress);
        log.info("Change event {} received for {}", event.getId(), url);

        return new WebhookAckResponse(event.getId(), event.getStatus().name(),
                regulation != null ? regulation.getId() : null, newVersionId, event.getReceivedAt());
    }

    @Transactional(readOnly = true)
    public List<ChangeEventResponse> list() {
        return eventRepository.findTop50ByOrderByReceivedAtDesc().stream().map(this::toResponse).toList();
    }

    private Long saveVersion(Regulation regulation, int versionNo, String content, String hash, String url) {
        return versionRepository.save(RegulationVersion.builder()
                .regulationId(regulation.getId())
                .versionNo(versionNo)
                .content(content)
                .contentHash(hash)
                .sourceUrl(url)
                .fetchedAt(LocalDateTime.now())
                .current(true)
                .build()).getId();
    }

    private RegulationSource resolveSource(JsonNode payload, String url) {
        String code = firstText(payload, "source_code", "source", "agency");
        if (code != null && !code.isBlank()) {
            Optional<RegulationSource> byCode = sourceRepository.findByCode(code.trim().toUpperCase());
            if (byCode.isPresent()) {
                return byCode.get();
            }
        }
        String host = hostOf(url);
        if (host == null) {
            return null;
        }
        for (RegulationSource source : sourceRepository.findByActiveTrue()) {
            String baseHost = hostOf(source.getBaseUrl());
            String watchHost = hostOf(source.getWatchUrl());
            if (matchesHost(host, baseHost) || matchesHost(host, watchHost)) {
                return source;
            }
        }
        return null;
    }

    private boolean matchesHost(String urlHost, String sourceHost) {
        if (sourceHost == null) {
            return false;
        }
        return urlHost.equals(sourceHost)
                || urlHost.endsWith("." + sourceHost)
                || sourceHost.endsWith("." + urlHost);
    }

    private String hostOf(String url) {
        if (url == null || url.isBlank()) {
            return null;
        }
        try {
            String candidate = url.contains("://") ? url : "https://" + url;
            String host = URI.create(candidate).getHost();
            return host != null && host.startsWith("www.") ? host.substring(4) : host;
        } catch (Exception ex) {
            return null;
        }
    }

    private String defaultTitle(String url) {
        String host = hostOf(url);
        return "Regulatory update" + (host != null ? " – " + host : "");
    }

    private String firstText(JsonNode payload, String... fields) {
        for (String field : fields) {
            JsonNode node = payload.get(field);
            if (node != null && !node.isNull()) {
                String value = node.isTextual() ? node.asText() : node.toString();
                if (value != null && !value.isBlank()) {
                    return value;
                }
            }
        }
        return null;
    }

    private ChangeEventResponse toResponse(ChangeEvent event) {
        String sourceCode = event.getSourceId() != null
                ? sourceRepository.findById(event.getSourceId()).map(RegulationSource::getCode).orElse(null)
                : null;
        return new ChangeEventResponse(event.getId(), event.getSourceId(), sourceCode,
                event.getRegulationId(), event.getStatus().name(), event.getPayloadUrl(),
                event.getOldVersionId(), event.getNewVersionId(), event.getError(),
                event.getReceivedAt(), event.getProcessedAt());
    }
}
