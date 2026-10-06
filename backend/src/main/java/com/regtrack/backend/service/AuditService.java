package com.regtrack.backend.service;

import com.regtrack.backend.dto.AuditDtos.AuditResponse;
import com.regtrack.backend.model.AuditLog;
import com.regtrack.backend.repository.AuditLogRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
public class AuditService {

    private final AuditLogRepository auditLogRepository;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String actorEmail, String actorRole, String action,
                       String entityType, Long entityId, String details, String ipAddress) {
        auditLogRepository.save(AuditLog.builder()
                .actorEmail(actorEmail)
                .actorRole(actorRole)
                .action(action)
                .entityType(entityType)
                .entityId(entityId)
                .details(details)
                .ipAddress(ipAddress)
                .build());
    }

    @Transactional(readOnly = true)
    public List<AuditResponse> list(String action) {
        List<AuditLog> logs = auditLogRepository.findTop200ByOrderByCreatedAtDesc();
        return logs.stream()
                .filter(log -> action == null || action.isBlank() || action.equalsIgnoreCase(log.getAction()))
                .map(this::toResponse)
                .toList();
    }

    private AuditResponse toResponse(AuditLog log) {
        return new AuditResponse(
                log.getId(), log.getActorEmail(), log.getActorRole(), log.getAction(),
                log.getEntityType(), log.getEntityId(), log.getDetails(),
                log.getIpAddress(), log.getCreatedAt());
    }
}
