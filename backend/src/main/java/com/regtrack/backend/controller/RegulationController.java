package com.regtrack.backend.controller;

import com.regtrack.backend.dto.RegulationDtos.RegulationResponse;
import com.regtrack.backend.dto.RegulationDtos.VersionDetailResponse;
import com.regtrack.backend.dto.RegulationDtos.VersionSummaryResponse;
import com.regtrack.backend.service.RegulationService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/regulations")
@RequiredArgsConstructor
public class RegulationController {

    private final RegulationService regulationService;

    @GetMapping
    public ResponseEntity<List<RegulationResponse>> list(
            @RequestParam(required = false, name = "source") String sourceCode) {
        return ResponseEntity.ok(regulationService.list(sourceCode));
    }

    @GetMapping("/{id}")
    public ResponseEntity<RegulationResponse> get(@PathVariable Long id) {
        return ResponseEntity.ok(regulationService.get(id));
    }

    @GetMapping("/{id}/versions")
    public ResponseEntity<List<VersionSummaryResponse>> versions(@PathVariable Long id) {
        return ResponseEntity.ok(regulationService.listVersions(id));
    }

    @GetMapping("/{id}/versions/{versionId}")
    public ResponseEntity<VersionDetailResponse> version(@PathVariable Long id,
                                                         @PathVariable Long versionId) {
        return ResponseEntity.ok(regulationService.getVersion(id, versionId));
    }
}
