package com.regtrack.backend.service;

import com.regtrack.backend.dto.AlertDtos.AlertCreateRequest;
import com.regtrack.backend.dto.AlertDtos.AlertResponse;
import com.regtrack.backend.exception.BadRequestException;
import com.regtrack.backend.exception.ForbiddenException;
import com.regtrack.backend.exception.NotFoundException;
import com.regtrack.backend.model.Alert;
import com.regtrack.backend.model.AlertStatus;
import com.regtrack.backend.model.ChangeEvent;
import com.regtrack.backend.model.Company;
import com.regtrack.backend.model.RelevanceLevel;
import com.regtrack.backend.model.Regulation;
import com.regtrack.backend.model.RegulationSource;
import com.regtrack.backend.model.Role;
import com.regtrack.backend.repository.AlertRepository;
import com.regtrack.backend.repository.ChangeEventRepository;
import com.regtrack.backend.repository.CompanyRepository;
import com.regtrack.backend.repository.RegulationRepository;
import com.regtrack.backend.repository.RegulationSourceRepository;
import com.regtrack.backend.security.UserPrincipal;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
public class AlertService {

    private final AlertRepository alertRepository;
    private final ChangeEventRepository eventRepository;
    private final RegulationRepository regulationRepository;
    private final RegulationSourceRepository sourceRepository;
    private final CompanyRepository companyRepository;
    private final AuditService auditService;

    @Transactional(readOnly = true)
    public List<AlertResponse> list(UserPrincipal principal, String status) {
        AlertStatus alertStatus = parseStatus(status);
        List<Alert> alerts;
        if (principal.role() == Role.ADMIN) {
            alerts = alertStatus == null
                    ? alertRepository.findAllByOrderByCreatedAtDesc()
                    : alertRepository.findByStatusOrderByCreatedAtDesc(alertStatus);
        } else {
            if (principal.companyId() == null) {
                return List.of();
            }
            alerts = alertStatus == null
                    ? alertRepository.findByCompanyIdOrderByCreatedAtDesc(principal.companyId())
                    : alertRepository.findByCompanyIdAndStatusOrderByCreatedAtDesc(
                            principal.companyId(), alertStatus);
        }
        return alerts.stream().map(this::toResponse).toList();
    }

    @Transactional
    public AlertResponse create(AlertCreateRequest request, UserPrincipal principal, String ipAddress) {
        if (principal.role() != Role.ADMIN
                && (principal.companyId() == null || !principal.companyId().equals(request.companyId()))) {
            throw new ForbiddenException("You can only create alerts for your own company");
        }
        if (!companyRepository.existsById(request.companyId())) {
            throw new NotFoundException("Company not found: " + request.companyId());
        }
        if (!eventRepository.existsById(request.changeEventId())) {
            throw new NotFoundException("Change event not found: " + request.changeEventId());
        }

        Alert alert = Alert.builder()
                .companyId(request.companyId())
                .changeEventId(request.changeEventId())
                .relevance(request.relevance() != null ? parseRelevance(request.relevance()) : RelevanceLevel.NONE)
                .summary(request.summary())
                .affectedAreas(request.affectedAreas())
                .effectiveDate(request.effectiveDate())
                .requiredAction(request.requiredAction())
                .status(AlertStatus.PENDING)
                .emailRecipients(request.emailRecipients())
                .build();
        Alert saved = alertRepository.save(alert);

        auditService.record(principal.email(), principal.role().name(), "ALERT_CREATED", "Alert",
                saved.getId(), "Alert created for company " + request.companyId(), ipAddress);
        return toResponse(saved);
    }

    @Transactional
    public AlertResponse updateStatus(Long id, String status, UserPrincipal principal, String ipAddress) {
        Alert alert = alertRepository.findById(id)
                .orElseThrow(() -> new NotFoundException("Alert not found: " + id));
        if (principal.role() != Role.ADMIN && !alert.getCompanyId().equals(principal.companyId())) {
            throw new ForbiddenException("You can only update alerts for your own company");
        }
        AlertStatus newStatus = parseStatus(status);
        if (newStatus == null) {
            throw new BadRequestException("Invalid alert status: " + status);
        }
        alert.setStatus(newStatus);
        Alert saved = alertRepository.save(alert);

        auditService.record(principal.email(), principal.role().name(), "ALERT_STATUS_CHANGED",
                "Alert", saved.getId(), "Alert status set to " + newStatus, ipAddress);
        return toResponse(saved);
    }

    private AlertStatus parseStatus(String status) {
        if (status == null || status.isBlank()) {
            return null;
        }
        try {
            return AlertStatus.valueOf(status.trim().toUpperCase());
        } catch (IllegalArgumentException ex) {
            throw new BadRequestException("Invalid alert status: " + status);
        }
    }

    private RelevanceLevel parseRelevance(String relevance) {
        try {
            return RelevanceLevel.valueOf(relevance.trim().toUpperCase());
        } catch (IllegalArgumentException ex) {
            throw new BadRequestException("Invalid relevance level: " + relevance);
        }
    }

    private AlertResponse toResponse(Alert alert) {
        String companyName = companyRepository.findById(alert.getCompanyId())
                .map(Company::getName).orElse(null);

        ChangeEvent event = eventRepository.findById(alert.getChangeEventId()).orElse(null);
        Regulation regulation = null;
        String sourceCode = null;
        if (event != null && event.getRegulationId() != null) {
            regulation = regulationRepository.findById(event.getRegulationId()).orElse(null);
        }
        if (regulation != null) {
            sourceCode = sourceRepository.findById(regulation.getSourceId())
                    .map(RegulationSource::getCode).orElse(null);
        }

        return new AlertResponse(
                alert.getId(), alert.getCompanyId(), companyName, alert.getChangeEventId(),
                alert.getRelevance().name(), alert.getSummary(), alert.getAffectedAreas(),
                alert.getEffectiveDate(), alert.getRequiredAction(), alert.getStatus().name(),
                alert.getEmailRecipients(), alert.getEmailSentAt(),
                regulation != null ? regulation.getTitle() : null,
                regulation != null ? regulation.getUrl() : null,
                sourceCode,
                alert.getCreatedAt());
    }
}
