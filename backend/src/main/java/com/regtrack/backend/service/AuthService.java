package com.regtrack.backend.service;

import com.regtrack.backend.dto.AuthDtos.AuthResponse;
import com.regtrack.backend.dto.AuthDtos.LoginRequest;
import com.regtrack.backend.dto.AuthDtos.RegisterRequest;
import com.regtrack.backend.dto.AuthDtos.UserResponse;
import com.regtrack.backend.exception.ConflictException;
import com.regtrack.backend.exception.UnauthorizedException;
import com.regtrack.backend.model.Company;
import com.regtrack.backend.model.CompanyProfile;
import com.regtrack.backend.model.Role;
import com.regtrack.backend.model.User;
import com.regtrack.backend.repository.CompanyProfileRepository;
import com.regtrack.backend.repository.CompanyRepository;
import com.regtrack.backend.repository.UserRepository;
import com.regtrack.backend.security.JwtService;
import com.regtrack.backend.security.UserPrincipal;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.Locale;

@Service
@RequiredArgsConstructor
public class AuthService {

    private final UserRepository userRepository;
    private final CompanyRepository companyRepository;
    private final CompanyProfileRepository companyProfileRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;
    private final AuditService auditService;

    @Transactional
    public AuthResponse register(RegisterRequest request, String ipAddress) {
        String email = request.email().trim().toLowerCase(Locale.ROOT);
        if (userRepository.existsByEmail(email)) {
            throw new ConflictException("An account with this email already exists");
        }

        Long companyId = null;
        if (request.companyName() != null && !request.companyName().isBlank()) {
            String companyName = request.companyName().trim();
            if (companyRepository.existsByNameIgnoreCase(companyName)) {
                throw new ConflictException("A company with this name already exists");
            }
            Company company = companyRepository.save(Company.builder()
                    .name(companyName)
                    .industry(request.industry())
                    .build());
            companyProfileRepository.save(CompanyProfile.builder()
                    .company(company)
                    .complianceContactEmail(email)
                    .build());
            companyId = company.getId();
        }

        User user = userRepository.save(User.builder()
                .email(email)
                .passwordHash(passwordEncoder.encode(request.password()))
                .fullName(request.fullName().trim())
                .role(Role.COMPLIANCE_OFFICER)
                .companyId(companyId)
                .enabled(true)
                .build());

        auditService.record(email, Role.COMPLIANCE_OFFICER.name(), "REGISTER", "User", user.getId(),
                "New account registered" + (companyId != null ? " with company " + request.companyName() : ""),
                ipAddress);

        return buildAuthResponse(user, companyId != null ? request.companyName().trim() : null);
    }

    @Transactional
    public AuthResponse login(LoginRequest request, String ipAddress) {
        String email = request.email().trim().toLowerCase(Locale.ROOT);
        User user = userRepository.findByEmail(email).orElse(null);

        if (user == null || !passwordEncoder.matches(request.password(), user.getPasswordHash())) {
            auditService.record(email, null, "LOGIN_FAILED", "User", null,
                    "Failed login attempt", ipAddress);
            throw new UnauthorizedException("Invalid email or password");
        }
        if (!Boolean.TRUE.equals(user.getEnabled())) {
            throw new UnauthorizedException("Account is disabled");
        }

        user.setLastLoginAt(LocalDateTime.now());
        userRepository.save(user);
        auditService.record(email, user.getRole().name(), "LOGIN", "User", user.getId(),
                "Successful login", ipAddress);

        return buildAuthResponse(user, companyNameOf(user.getCompanyId()));
    }

    @Transactional(readOnly = true)
    public UserResponse me(UserPrincipal principal) {
        User user = userRepository.findById(principal.id())
                .orElseThrow(() -> new UnauthorizedException("Account no longer exists"));
        return toUserResponse(user, companyNameOf(user.getCompanyId()));
    }

    private AuthResponse buildAuthResponse(User user, String companyName) {
        String token = jwtService.generate(new UserPrincipal(
                user.getId(), user.getEmail(), user.getRole(), user.getCompanyId()));
        return new AuthResponse(token, "Bearer", jwtService.expirationSeconds(),
                toUserResponse(user, companyName));
    }

    private UserResponse toUserResponse(User user, String companyName) {
        return new UserResponse(user.getId(), user.getEmail(), user.getFullName(),
                user.getRole().name(), user.getCompanyId(), companyName);
    }

    private String companyNameOf(Long companyId) {
        if (companyId == null) {
            return null;
        }
        return companyRepository.findById(companyId).map(Company::getName).orElse(null);
    }
}
