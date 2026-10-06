package com.regtrack.backend.service;

import com.regtrack.backend.dto.ExtractionDtos.ExtractRequest;
import com.regtrack.backend.dto.ExtractionDtos.ExtractResponse;
import com.regtrack.backend.dto.ExtractionDtos.TriggerExtractionResponse;
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
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestClient;

import java.net.URI;
import java.time.LocalDateTime;
import java.util.Optional;

@Service
@Slf4j
public class ExtractionService {

    private final RestClient restClient;
    private final RegulationRepository regulationRepository;
    private final RegulationVersionRepository versionRepository;
    private final RegulationSourceRepository sourceRepository;
    private final ChangeEventRepository eventRepository;
    private final AuditService auditService;

    public ExtractionService(
            @Value("${app.extraction-worker.url:http://extraction-worker:8000}") String extractionWorkerUrl,
            RegulationRepository regulationRepository,
            RegulationVersionRepository versionRepository,
            RegulationSourceRepository sourceRepository,
            ChangeEventRepository eventRepository,
            AuditService auditService
    ) {
        this.restClient = RestClient.builder()
                .baseUrl(extractionWorkerUrl)
                .build();
        this.regulationRepository = regulationRepository;
        this.versionRepository = versionRepository;
        this.sourceRepository = sourceRepository;
        this.eventRepository = eventRepository;
        this.auditService = auditService;
    }

    /**
     * Directly extract full content from a URL via the Python Extraction Worker.
     */
    public ExtractResponse extract(String url, String strategy) {
        log.info("Requesting extraction for URL: {} using strategy: {}", url, strategy);
        try {
            ExtractRequest request = new ExtractRequest(
                    url,
                    strategy != null ? strategy : "AUTO",
                    true,
                    true,
                    30
            );

            return restClient.post()
                    .uri("/extract")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(request)
                    .retrieve()
                    .body(ExtractResponse.class);
        } catch (Exception ex) {
            log.error("Failed to extract content from {}: {}", url, ex.getMessage(), ex);
            throw new BadRequestException("Extraction worker failed: " + ex.getMessage());
        }
    }

    /**
     * Trigger extraction for a regulation and create a new version if content changed.
     */
    @Transactional
    public TriggerExtractionResponse triggerExtractionAndSaveVersion(String url, String strategy, String username) {
        ExtractResponse extracted = extract(url, strategy);

        if (extracted == null || !Boolean.TRUE.equals(extracted.success()) || extracted.markdown() == null) {
            String errorMsg = extracted != null ? extracted.error() : "No response from extraction service";
            throw new BadRequestException("Extraction failed for " + url + ": " + errorMsg);
        }

        Regulation SourceOrReg = null;
        Regulation regulation = regulationRepository.findByUrl(url).orElse(null);

        if (regulation == null) {
            RegulationSource source = resolveSource(url);
            String title = extracted.title() != null && !extracted.title().isBlank()
                    ? extracted.title().trim()
                    : "Extracted update - " + hostOf(url);

            regulation = regulationRepository.save(Regulation.builder()
                    .sourceId(source != null ? source.getId() : null)
                    .title(title)
                    .url(url)
                    .category(extracted.metadata() != null ? extracted.metadata().get("category") : "GENERAL")
                    .build());
        } else if (extracted.title() != null && !extracted.title().isBlank()) {
            regulation.setTitle(extracted.title().trim());
            regulation = regulationRepository.save(regulation);
        }

        String markdownContent = extracted.markdown();
        String contentHash = WebhookHmacFilter.sha256Hex(markdownContent);
        Optional<RegulationVersion> currentVersionOpt = versionRepository.findFirstByRegulationIdAndCurrentTrue(regulation.getId());

        boolean contentChanged = false;
        Long newVersionId = null;

        if (currentVersionOpt.isPresent()) {
            RegulationVersion current = currentVersionOpt.get();
            if (!contentHash.equals(current.getContentHash())) {
                current.setCurrent(false);
                versionRepository.save(current);

                newVersionId = saveVersion(regulation, current.getVersionNo() + 1, markdownContent, contentHash, url);
                contentChanged = true;
            } else {
                newVersionId = current.getId();
            }
        } else {
            newVersionId = saveVersion(regulation, 1, markdownContent, contentHash, url);
            contentChanged = true;
        }

        if (contentChanged) {
            eventRepository.save(ChangeEvent.builder()
                    .sourceId(regulation.getSourceId())
                    .regulationId(regulation.getId())
                    .oldVersionId(currentVersionOpt.map(RegulationVersion::getId).orElse(null))
                    .newVersionId(newVersionId)
                    .status(ChangeStatus.RECEIVED)
                    .payloadUrl(url)
                    .payloadJson("{\"triggered_by\": \"" + username + "\", \"strategy\": \"" + extracted.strategyUsed() + "\"}")
                    .receivedAt(LocalDateTime.now())
                    .build());
        }

        auditService.record(username != null ? username : "system", "USER", "EXTRACTION_TRIGGERED",
                "Regulation", regulation.getId(),
                "Strategy: " + extracted.strategyUsed() + ", Content changed: " + contentChanged, "127.0.0.1");

        return new TriggerExtractionResponse(
                regulation.getId(),
                newVersionId,
                url,
                extracted.strategyUsed(),
                contentChanged,
                "SUCCESS"
        );
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

    private RegulationSource resolveSource(String url) {
        String host = hostOf(url);
        if (host == null) return null;
        for (RegulationSource source : sourceRepository.findByActiveTrue()) {
            String baseHost = hostOf(source.getBaseUrl());
            String watchHost = hostOf(source.getWatchUrl());
            if ((baseHost != null && host.contains(baseHost)) || (watchHost != null && host.contains(watchHost))) {
                return source;
            }
        }
        return null;
    }

    private String hostOf(String url) {
        if (url == null || url.isBlank()) return null;
        try {
            String candidate = url.contains("://") ? url : "https://" + url;
            String host = URI.create(candidate).getHost();
            return host != null && host.startsWith("www.") ? host.substring(4) : host;
        } catch (Exception ex) {
            return null;
        }
    }
}
