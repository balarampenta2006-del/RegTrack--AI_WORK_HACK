package com.regtrack.backend.controller;

import com.regtrack.backend.dto.CompanyDtos.CompanyRequest;
import com.regtrack.backend.dto.CompanyDtos.CompanyResponse;
import com.regtrack.backend.dto.CompanyDtos.ProfileRequest;
import com.regtrack.backend.dto.CompanyDtos.ProfileResponse;
import com.regtrack.backend.security.CurrentUser;
import com.regtrack.backend.security.UserPrincipal;
import com.regtrack.backend.service.CompanyService;
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
@RequestMapping("/api/companies")
@RequiredArgsConstructor
public class CompanyController {

    private final CompanyService companyService;

    @PostMapping
    public ResponseEntity<CompanyResponse> create(@Valid @RequestBody CompanyRequest request,
                                                  Authentication authentication,
                                                  HttpServletRequest http) {
        UserPrincipal principal = CurrentUser.require(authentication);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(companyService.create(request, principal, clientIp(http)));
    }

    @GetMapping
    public ResponseEntity<List<CompanyResponse>> list(Authentication authentication) {
        UserPrincipal principal = CurrentUser.require(authentication);
        return ResponseEntity.ok(companyService.list(principal));
    }

    @GetMapping("/{id}")
    public ResponseEntity<CompanyResponse> get(@PathVariable Long id, Authentication authentication) {
        UserPrincipal principal = CurrentUser.require(authentication);
        return ResponseEntity.ok(companyService.get(id, principal));
    }

    @PutMapping("/{id}")
    public ResponseEntity<CompanyResponse> update(@PathVariable Long id,
                                                  @Valid @RequestBody CompanyRequest request,
                                                  Authentication authentication,
                                                  HttpServletRequest http) {
        UserPrincipal principal = CurrentUser.require(authentication);
        return ResponseEntity.ok(companyService.update(id, request, principal, clientIp(http)));
    }

    @PutMapping("/{id}/profile")
    public ResponseEntity<ProfileResponse> upsertProfile(@PathVariable Long id,
                                                         @Valid @RequestBody ProfileRequest request,
                                                         Authentication authentication,
                                                         HttpServletRequest http) {
        UserPrincipal principal = CurrentUser.require(authentication);
        return ResponseEntity.ok(companyService.upsertProfile(id, request, principal, clientIp(http)));
    }

    @GetMapping("/{id}/profile")
    public ResponseEntity<ProfileResponse> getProfile(@PathVariable Long id, Authentication authentication) {
        UserPrincipal principal = CurrentUser.require(authentication);
        return ResponseEntity.ok(companyService.getProfile(id, principal));
    }

    private String clientIp(HttpServletRequest request) {
        String forwarded = request.getHeader("X-Forwarded-For");
        if (forwarded != null && !forwarded.isBlank()) {
            return forwarded.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }
}
