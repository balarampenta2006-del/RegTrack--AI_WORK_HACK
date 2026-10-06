package com.regtrack.backend.dto;

import jakarta.validation.constraints.NotNull;

import java.time.LocalDate;
import java.time.LocalDateTime;

public final class AlertDtos {

    private AlertDtos() {
    }

    public record AlertCreateRequest(
            @NotNull Long companyId,
            @NotNull Long changeEventId,
            String relevance,
            String summary,
            String affectedAreas,
            LocalDate effectiveDate,
            String requiredAction,
            String emailRecipients) {
    }

    public record AlertStatusRequest(
            @NotNull String status) {
    }

    public record AlertResponse(
            Long id,
            Long companyId,
            String companyName,
            Long changeEventId,
            String relevance,
            String summary,
            String affectedAreas,
            LocalDate effectiveDate,
            String requiredAction,
            String status,
            String emailRecipients,
            LocalDateTime emailSentAt,
            String regulationTitle,
            String regulationUrl,
            String sourceCode,
            LocalDateTime createdAt) {
    }
}
