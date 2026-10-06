package com.regtrack.backend.controller;

import com.regtrack.backend.dto.AuditDtos.AuditResponse;
import com.regtrack.backend.service.AuditService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/audit")
@RequiredArgsConstructor
public class AuditController {

    private final AuditService auditService;

    @GetMapping
    public ResponseEntity<List<AuditResponse>> list(
            @RequestParam(required = false) String action) {
        return ResponseEntity.ok(auditService.list(action));
    }
}
