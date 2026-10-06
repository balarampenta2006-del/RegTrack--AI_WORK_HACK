package com.regtrack.backend.dto;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

public class ExtractionDtos {

    public record ExtractRequest(
            String url,
            String strategy, // AUTO, BEAUTIFUL_SOUP, FIRECRAWL
            Boolean includeTables,
            Boolean extractPdfLinks,
            Integer timeoutSeconds
    ) {}

    public record ExtractResponse(
            String url,
            String title,
            String markdown,
            String contentHash,
            String strategyUsed,
            Boolean success,
            String error,
            List<DocumentLinkDto> documentLinks,
            List<TableDto> tables,
            Map<String, String> metadata,
            LocalDateTime extractedAt
    ) {}

    public record DocumentLinkDto(
            String url,
            String text,
            String fileType
    ) {}

    public record TableDto(
            String caption,
            List<String> headers,
            List<List<String>> rows
    ) {}

    public record BatchExtractRequest(
            List<String> urls,
            String strategy
    ) {}

    public record TriggerExtractionResponse(
            Long regulationId,
            Long versionId,
            String url,
            String strategyUsed,
            boolean contentChanged,
            String status
    ) {}
}
