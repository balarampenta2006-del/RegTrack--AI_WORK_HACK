package com.regtrack.backend.controller;

import com.regtrack.backend.dto.AlertDtos.AlertCreateRequest;
import com.regtrack.backend.dto.AlertDtos.AlertResponse;
import com.regtrack.backend.dto.AlertDtos.AlertStatusRequest;
import com.regtrack.backend.security.CurrentUser;
import com.regtrack.backend.security.UserPrincipal;
import com.regtrack.backend.service.AlertService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/alerts")
@RequiredArgsConstructor
public class AlertController {

    private final AlertService alertService;

    @GetMapping
    public ResponseEntity<List<AlertResponse>> list(
            @RequestParam(required = false) String status,
            Authentication authentication) {
        UserPrincipal principal = CurrentUser.require(authentication);
        return ResponseEntity.ok(alertService.list(principal, status));
    }

    @PostMapping
    public ResponseEntity<AlertResponse> create(@Valid @RequestBody AlertCreateRequest request,
                                                Authentication authentication,
                                                HttpServletRequest http) {
        UserPrincipal principal = CurrentUser.require(authentication);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(alertService.create(request, principal, clientIp(http)));
    }

    @PatchMapping("/{id}/status")
    public ResponseEntity<AlertResponse> updateStatus(@PathVariable Long id,
                                                      @RequestBody Map<String, String> body,
                                                      Authentication authentication,
                                                      HttpServletRequest http) {
        UserPrincipal principal = CurrentUser.require(authentication);
        String status = body.get("status");
        if (status == null || status.isBlank()) {
            return ResponseEntity.badRequest().build();
        }
        return ResponseEntity.ok(alertService.updateStatus(id, status, principal, clientIp(http)));
    }

    private String clientIp(HttpServletRequest request) {
        String forwarded = request.getHeader("X-Forwarded-For");
        if (forwarded != null && !forwarded.isBlank()) {
            return forwarded.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }
}
