package com.regtrack.backend.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import java.time.LocalDateTime;

public final class CompanyDtos {

    private CompanyDtos() {
    }

    public record CompanyRequest(
            @NotBlank @Size(max = 190) String name,
            @Size(max = 120) String industry,
            @Size(max = 255) String website,
            @Size(max = 2000) String description,
            @Size(max = 255) String jurisdictions) {
    }

    public record CompanyResponse(
            Long id,
            String name,
            String industry,
            String website,
            String description,
            String jurisdictions,
            LocalDateTime createdAt) {
    }

    public record ProfileRequest(
            @Size(max = 4000) String industrySectors,
            @Size(max = 255) String regulatoryBodies,
            @Size(max = 255) String jurisdictions,
            @Size(max = 190) String complianceContactEmail,
            Boolean notificationEnabled,
            @Size(max = 4000) String notes) {
    }

    public record ProfileResponse(
            Long id,
            Long companyId,
            String industrySectors,
            String regulatoryBodies,
            String jurisdictions,
            String complianceContactEmail,
            Boolean notificationEnabled,
            String notes,
            LocalDateTime updatedAt) {
    }
}
