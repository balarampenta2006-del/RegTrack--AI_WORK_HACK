package com.regtrack.backend.dto;

import java.time.LocalDateTime;

public final class AuditDtos {

    private AuditDtos() {
    }

    public record AuditResponse(
            Long id,
            String actorEmail,
            String actorRole,
            String action,
            String entityType,
            Long entityId,
            String details,
            String ipAddress,
            LocalDateTime createdAt) {
    }
}
