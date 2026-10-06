package com.regtrack.backend.dto;

import java.time.LocalDate;
import java.time.LocalDateTime;

public final class RegulationDtos {

    private RegulationDtos() {
    }

    public record RegulationResponse(
            Long id,
            Long sourceId,
            String sourceCode,
            String title,
            String identifier,
            String url,
            String category,
            LocalDate publishedDate,
            LocalDate effectiveDate,
            Integer versionCount,
            Long currentVersionId,
            LocalDateTime createdAt) {
    }

    public record VersionSummaryResponse(
            Long id,
            Long regulationId,
            Integer versionNo,
            String contentHash,
            String sourceUrl,
            LocalDateTime fetchedAt,
            Boolean current) {
    }

    public record VersionDetailResponse(
            Long id,
            Long regulationId,
            Integer versionNo,
            String content,
            String contentHash,
            String storagePath,
            String sourceUrl,
            LocalDateTime fetchedAt,
            Boolean current) {
    }
}
