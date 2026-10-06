package com.regtrack.backend.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

@Entity
@Table(name = "change_events")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ChangeEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "source_id")
    private Long sourceId;

    @Column(name = "regulation_id")
    private Long regulationId;

    @Column(name = "old_version_id")
    private Long oldVersionId;

    @Column(name = "new_version_id")
    private Long newVersionId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    @Builder.Default
    private ChangeStatus status = ChangeStatus.RECEIVED;

    @Column(name = "payload_url", length = 512)
    private String payloadUrl;

    @Column(name = "payload_json", columnDefinition = "MEDIUMTEXT")
    private String payloadJson;

    @Column(columnDefinition = "TEXT")
    private String error;

    @Column(name = "received_at", nullable = false)
    private LocalDateTime receivedAt;

    @Column(name = "processed_at")
    private LocalDateTime processedAt;
}
