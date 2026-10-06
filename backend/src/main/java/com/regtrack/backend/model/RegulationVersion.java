package com.regtrack.backend.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
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
@Table(name = "regulation_versions")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RegulationVersion {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "regulation_id", nullable = false)
    private Long regulationId;

    @Column(name = "version_no", nullable = false)
    private Integer versionNo;

    @Column(name = "content", columnDefinition = "MEDIUMTEXT")
    private String content;

    @Column(name = "content_hash", length = 64)
    private String contentHash;

    @Column(name = "storage_path", length = 512)
    private String storagePath;

    @Column(name = "source_url", length = 512)
    private String sourceUrl;

    @Column(name = "fetched_at", nullable = false)
    private LocalDateTime fetchedAt;

    @Column(name = "is_current", nullable = false)
    @Builder.Default
    private Boolean current = false;
}
