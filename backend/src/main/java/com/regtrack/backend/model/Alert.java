package com.regtrack.backend.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDate;
import java.time.LocalDateTime;

@Entity
@Table(name = "alerts")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Alert {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "company_id", nullable = false)
    private Long companyId;

    @Column(name = "change_event_id", nullable = false)
    private Long changeEventId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    @Builder.Default
    private RelevanceLevel relevance = RelevanceLevel.NONE;

    @Column(columnDefinition = "TEXT")
    private String summary;

    @Column(name = "affected_areas", columnDefinition = "TEXT")
    private String affectedAreas;

    @Column(name = "effective_date")
    private LocalDate effectiveDate;

    @Column(name = "required_action", columnDefinition = "TEXT")
    private String requiredAction;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    @Builder.Default
    private AlertStatus status = AlertStatus.PENDING;

    @Column(name = "email_recipients", length = 512)
    private String emailRecipients;

    @Column(name = "email_sent_at")
    private LocalDateTime emailSentAt;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;

    @PrePersist
    void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    void onUpdate() {
        updatedAt = LocalDateTime.now();
    }
}
