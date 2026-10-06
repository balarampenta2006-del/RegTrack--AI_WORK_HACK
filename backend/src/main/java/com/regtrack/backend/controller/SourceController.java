package com.regtrack.backend.controller;

import com.regtrack.backend.dto.SourceDtos.SourceRequest;
import com.regtrack.backend.dto.SourceDtos.SourceResponse;
import com.regtrack.backend.security.CurrentUser;
import com.regtrack.backend.security.UserPrincipal;
import com.regtrack.backend.service.SourceService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/sources")
@RequiredArgsConstructor
public class SourceController {

    private final SourceService sourceService;

    @PostMapping
    public ResponseEntity<SourceResponse> create(@Valid @RequestBody SourceRequest request,
                                                 Authentication authentication,
                                                 HttpServletRequest http) {
        UserPrincipal principal = CurrentUser.require(authentication);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(sourceService.create(request, principal, clientIp(http)));
    }

    @PutMapping("/{id}")
    public ResponseEntity<SourceResponse> update(@PathVariable Long id,
                                                 @Valid @RequestBody SourceRequest request,
                                                 Authentication authentication,
                                                 HttpServletRequest http) {
        UserPrincipal principal = CurrentUser.require(authentication);
        return ResponseEntity.ok(sourceService.update(id, request, principal, clientIp(http)));
    }

    @GetMapping
    public ResponseEntity<List<SourceResponse>> list() {
        return ResponseEntity.ok(sourceService.list());
    }

    @GetMapping("/{id}")
    public ResponseEntity<SourceResponse> get(@PathVariable Long id) {
        return ResponseEntity.ok(sourceService.get(id));
    }

    private String clientIp(HttpServletRequest request) {
        String forwarded = request.getHeader("X-Forwarded-For");
        if (forwarded != null && !forwarded.isBlank()) {
            return forwarded.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }
}
