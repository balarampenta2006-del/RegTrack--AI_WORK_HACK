package com.regtrack.backend.controller;

import com.regtrack.backend.dto.DiffDtos.VersionDiffResponse;
import com.regtrack.backend.dto.DiffDtos.VersionSummaryDto;
import com.regtrack.backend.model.RegulationVersion;
import com.regtrack.backend.service.DiffService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1/regulations/{regulationId}")
@RequiredArgsConstructor
public class DiffController {

    private final DiffService diffService;

    /**
     * Get all version history records for a regulation.
     */
    @GetMapping("/versions")
    public ResponseEntity<List<VersionSummaryDto>> getVersions(@PathVariable Long regulationId) {
        return ResponseEntity.ok(diffService.getVersions(regulationId));
    }

    /**
     * Get details and content of a specific version number.
     */
    @GetMapping("/versions/{versionNo}")
    public ResponseEntity<RegulationVersion> getVersion(
            @PathVariable Long regulationId,
            @PathVariable Integer versionNo
    ) {
        return ResponseEntity.ok(diffService.getVersion(regulationId, versionNo));
    }

    /**
     * Compare two versions of a regulation (or latest 2 by default if parameters are omitted).
     */
    @GetMapping("/diff")
    public ResponseEntity<VersionDiffResponse> compareDiff(
            @PathVariable Long regulationId,
            @RequestParam(required = false) Integer oldVersionNo,
            @RequestParam(required = false) Integer newVersionNo
    ) {
        return ResponseEntity.ok(diffService.compareVersions(regulationId, oldVersionNo, newVersionNo));
    }

    /**
     * Download or view unified diff (.patch) text format.
     */
    @GetMapping(value = "/diff/patch", produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> getUnifiedPatch(
            @PathVariable Long regulationId,
            @RequestParam(required = false) Integer oldVersionNo,
            @RequestParam(required = false) Integer newVersionNo
    ) {
        VersionDiffResponse diff = diffService.compareVersions(regulationId, oldVersionNo, newVersionNo);
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "inline; filename=\"regulation-" + regulationId + "-v" + diff.oldVersionNo() + "-v" + diff.newVersionNo() + ".patch\"")
                .body(diff.unifiedPatch());
    }
}
