package com.regtrack.backend.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
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

import java.time.LocalDateTime;

@Entity
@Table(name = "regulation_sources")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RegulationSource {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 32)
    private String code;

    @Column(nullable = false, length = 190)
    private String name;

    @Column(length = 64)
    private String agency;

    @Column(name = "base_url", length = 255)
    private String baseUrl;

    @Column(name = "watch_url", length = 512)
    private String watchUrl;

    @Column(name = "change_detection_id", length = 128)
    private String changeDetectionId;

    @Column(nullable = false)
    @Builder.Default
    private Boolean active = true;

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
