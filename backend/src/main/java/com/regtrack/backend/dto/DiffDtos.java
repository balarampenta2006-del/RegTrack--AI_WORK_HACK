package com.regtrack.backend.dto;

import java.time.LocalDateTime;
import java.util.List;

public class DiffDtos {

    public enum DiffType {
        EQUAL, ADD, DELETE, MODIFY
    }

    public enum ClauseChangeType {
        UNCHANGED, ADDED, DELETED, MODIFIED
    }

    public enum MetricType {
        DEADLINE, NUMERIC_VALUE, PENALTY, COMPLIANCE_KEYWORD
    }

    public record VersionSummaryDto(
            Long id,
            Long regulationId,
            Integer versionNo,
            String contentHash,
            String sourceUrl,
            LocalDateTime fetchedAt,
            Boolean current,
            Integer contentLength
    ) {}

    public record DiffLineDto(
            Integer oldLineNumber,
            Integer newLineNumber,
            DiffType type,
            String text
    ) {}

    public record ClauseDiffDto(
            String clauseHeader,
            ClauseChangeType changeType,
            String oldContent,
            String newContent,
            String summaryOfChanges
    ) {}

    public record MetricChangeDto(
            MetricType metricType,
            String description,
            String oldValue,
            String newValue,
            String contextSnippet
    ) {}

    public record DiffStatsDto(
            int totalLinesOld,
            int totalLinesNew,
            int additions,
            int deletions,
            int modifications,
            int unchanged,
            double similarityPercentage
    ) {}

    public record VersionDiffResponse(
            Long regulationId,
            String regulationTitle,
            Integer oldVersionNo,
            Integer newVersionNo,
            Long oldVersionId,
            Long newVersionId,
            DiffStatsDto stats,
            List<DiffLineDto> lineDiffs,
            List<ClauseDiffDto> clauseDiffs,
            List<MetricChangeDto> metricChanges,
            String unifiedPatch,
            LocalDateTime computedAt
    ) {}
}
