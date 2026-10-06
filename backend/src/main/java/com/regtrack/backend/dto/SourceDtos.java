package com.regtrack.backend.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import java.time.LocalDateTime;

public final class SourceDtos {

    private SourceDtos() {
    }

    public record SourceRequest(
            @NotBlank @Size(max = 32) String code,
            @NotBlank @Size(max = 190) String name,
            @Size(max = 64) String agency,
            @Size(max = 255) String baseUrl,
            @Size(max = 512) String watchUrl,
            @Size(max = 128) String changeDetectionId,
            Boolean active) {
    }

    public record SourceResponse(
            Long id,
            String code,
            String name,
            String agency,
            String baseUrl,
            String watchUrl,
            String changeDetectionId,
            Boolean active,
            LocalDateTime createdAt) {
    }
}
