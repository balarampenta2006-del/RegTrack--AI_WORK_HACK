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

import java.time.LocalDate;
import java.time.LocalDateTime;

@Entity
@Table(name = "regulations")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Regulation {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "source_id", nullable = false)
    private Long sourceId;

    @Column(nullable = false, length = 512)
    private String title;

    @Column(length = 120)
    private String identifier;

    @Column(nullable = false, unique = true, length = 512)
    private String url;

    @Column(length = 120)
    private String category;

    @Column(name = "published_date")
    private LocalDate publishedDate;

    @Column(name = "effective_date")
    private LocalDate effectiveDate;

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
