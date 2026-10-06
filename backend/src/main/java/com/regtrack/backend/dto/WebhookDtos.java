package com.regtrack.backend.dto;

import java.time.LocalDateTime;

public final class WebhookDtos {

    private WebhookDtos() {
    }

    public record WebhookAckResponse(
            Long eventId,
            String status,
            Long regulationId,
            Long newVersionId,
            LocalDateTime receivedAt) {
    }

    public record ChangeEventResponse(
            Long id,
            Long sourceId,
            String sourceCode,
            Long regulationId,
            String status,
            String payloadUrl,
            Long oldVersionId,
            Long newVersionId,
            String error,
            LocalDateTime receivedAt,
            LocalDateTime processedAt) {
    }
}
