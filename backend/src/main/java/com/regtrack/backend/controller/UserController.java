package com.regtrack.backend.controller;

import com.regtrack.backend.dto.AuthDtos.UserResponse;
import com.regtrack.backend.security.CurrentUser;
import com.regtrack.backend.security.UserPrincipal;
import com.regtrack.backend.service.AuthService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class UserController {

    private final AuthService authService;

    @GetMapping("/me")
    public ResponseEntity<UserResponse> me(Authentication authentication) {
        UserPrincipal principal = CurrentUser.require(authentication);
        return ResponseEntity.ok(authService.me(principal));
    }
}
