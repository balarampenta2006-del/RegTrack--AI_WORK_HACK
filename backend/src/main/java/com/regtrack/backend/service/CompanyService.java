package com.regtrack.backend.service;

import com.regtrack.backend.dto.CompanyDtos.CompanyRequest;
import com.regtrack.backend.dto.CompanyDtos.CompanyResponse;
import com.regtrack.backend.dto.CompanyDtos.ProfileRequest;
import com.regtrack.backend.dto.CompanyDtos.ProfileResponse;
import com.regtrack.backend.exception.ConflictException;
import com.regtrack.backend.exception.ForbiddenException;
import com.regtrack.backend.exception.NotFoundException;
import com.regtrack.backend.model.Company;
import com.regtrack.backend.model.CompanyProfile;
import com.regtrack.backend.model.Role;
import com.regtrack.backend.repository.CompanyProfileRepository;
import com.regtrack.backend.repository.CompanyRepository;
import com.regtrack.backend.security.UserPrincipal;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
public class CompanyService {

    private final CompanyRepository companyRepository;
    private final CompanyProfileRepository companyProfileRepository;
    private final AuditService auditService;

    @Transactional
    public CompanyResponse create(CompanyRequest request, UserPrincipal principal, String ipAddress) {
        if (companyRepository.existsByNameIgnoreCase(request.name().trim())) {
            throw new ConflictException("A company with this name already exists");
        }
        Company company = companyRepository.save(Company.builder()
                .name(request.name().trim())
                .industry(request.industry())
                .website(request.website())
                .description(request.description())
                .jurisdictions(request.jurisdictions())
                .build());
        auditService.record(principal.email(), principal.role().name(), "COMPANY_CREATED",
                "Company", company.getId(), "Created company: " + company.getName(), ipAddress);
        return toResponse(company);
    }

    @Transactional(readOnly = true)
    public List<CompanyResponse> list(UserPrincipal principal) {
        List<Company> companies = isAdmin(principal)
                ? companyRepository.findAll()
                : companyRepository.findAllById(principal.companyId() != null
                ? List.of(principal.companyId())
                : List.of());
        return companies.stream().map(this::toResponse).toList();
    }

    @Transactional(readOnly = true)
    public CompanyResponse get(Long id, UserPrincipal principal) {
        return toResponse(loadAuthorized(id, principal));
    }

    @Transactional
    public CompanyResponse update(Long id, CompanyRequest request, UserPrincipal principal, String ipAddress) {
        Company company = loadAuthorized(id, principal);
        company.setName(request.name().trim());
        company.setIndustry(request.industry());
        company.setWebsite(request.website());
        company.setDescription(request.description());
        company.setJurisdictions(request.jurisdictions());
        Company saved = companyRepository.save(company);
        auditService.record(principal.email(), principal.role().name(), "COMPANY_UPDATED",
                "Company", saved.getId(), "Updated company: " + saved.getName(), ipAddress);
        return toResponse(saved);
    }

    @Transactional
    public ProfileResponse upsertProfile(Long companyId, ProfileRequest request,
                                         UserPrincipal principal, String ipAddress) {
        loadAuthorized(companyId, principal);
        Company company = companyRepository.findById(companyId)
                .orElseThrow(() -> new NotFoundException("Company not found: " + companyId));

        CompanyProfile profile = companyProfileRepository.findByCompanyId(companyId)
                .orElseGet(() -> CompanyProfile.builder().company(company).build());

        profile.setIndustrySectors(request.industrySectors());
        profile.setRegulatoryBodies(request.regulatoryBodies());
        profile.setJurisdictions(request.jurisdictions() != null ? request.jurisdictions() : company.getJurisdictions());
        profile.setComplianceContactEmail(request.complianceContactEmail());
        if (request.notificationEnabled() != null) {
            profile.setNotificationEnabled(request.notificationEnabled());
        }
        profile.setNotes(request.notes());

        CompanyProfile saved = companyProfileRepository.save(profile);
        auditService.record(principal.email(), principal.role().name(), "PROFILE_UPDATED",
                "CompanyProfile", saved.getId(), "Updated compliance profile for company " + companyId,
                ipAddress);
        return toProfileResponse(saved);
    }

    @Transactional(readOnly = true)
    public ProfileResponse getProfile(Long companyId, UserPrincipal principal) {
        loadAuthorized(companyId, principal);
        return companyProfileRepository.findByCompanyId(companyId)
                .map(this::toProfileResponse)
                .orElseThrow(() -> new NotFoundException("No profile found for company: " + companyId));
    }

    private Company loadAuthorized(Long id, UserPrincipal principal) {
        Company company = companyRepository.findById(id)
                .orElseThrow(() -> new NotFoundException("Company not found: " + id));
        if (!isAdmin(principal) && !id.equals(principal.companyId())) {
            throw new ForbiddenException("You can only access your own company");
        }
        return company;
    }

    private boolean isAdmin(UserPrincipal principal) {
        return principal.role() == Role.ADMIN;
    }

    private CompanyResponse toResponse(Company company) {
        return new CompanyResponse(company.getId(), company.getName(), company.getIndustry(),
                company.getWebsite(), company.getDescription(), company.getJurisdictions(),
                company.getCreatedAt());
    }

    private ProfileResponse toProfileResponse(CompanyProfile profile) {
        return new ProfileResponse(profile.getId(), profile.getCompany().getId(),
                profile.getIndustrySectors(), profile.getRegulatoryBodies(), profile.getJurisdictions(),
                profile.getComplianceContactEmail(), profile.getNotificationEnabled(),
                profile.getNotes(), profile.getUpdatedAt());
    }
}
