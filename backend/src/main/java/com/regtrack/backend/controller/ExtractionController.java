package com.regtrack.backend.controller;

import com.regtrack.backend.dto.ExtractionDtos.ExtractRequest;
import com.regtrack.backend.dto.ExtractionDtos.ExtractResponse;
import com.regtrack.backend.dto.ExtractionDtos.TriggerExtractionResponse;
import com.regtrack.backend.service.ExtractionService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/extractions")
@RequiredArgsConstructor
public class ExtractionController {

    private final ExtractionService extractionService;

    /**
     * Preview extraction results for a target URL without persisting a version.
     */
    @PostMapping("/extract")
    public ResponseEntity<ExtractResponse> extractContent(@Valid @RequestBody ExtractRequest request) {
        ExtractResponse response = extractionService.extract(request.url(), request.strategy());
        return ResponseEntity.ok(response);
    }

    /**
     * Trigger extraction for a URL and create/update Regulation & RegulationVersion records.
     */
    @PostMapping("/trigger")
    public ResponseEntity<TriggerExtractionResponse> triggerExtraction(
            @Valid @RequestBody ExtractRequest request,
            Authentication authentication
    ) {
        String username = authentication != null ? authentication.getName() : "system";
        TriggerExtractionResponse response = extractionService.triggerExtractionAndSaveVersion(
                request.url(), request.strategy(), username
        );
        return ResponseEntity.ok(response);
    }
}
