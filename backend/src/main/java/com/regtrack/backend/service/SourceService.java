package com.regtrack.backend.service;

import com.regtrack.backend.dto.SourceDtos.SourceRequest;
import com.regtrack.backend.dto.SourceDtos.SourceResponse;
import com.regtrack.backend.exception.ConflictException;
import com.regtrack.backend.exception.NotFoundException;
import com.regtrack.backend.model.RegulationSource;
import com.regtrack.backend.repository.RegulationSourceRepository;
import com.regtrack.backend.security.UserPrincipal;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
public class SourceService {

    private final RegulationSourceRepository sourceRepository;
    private final AuditService auditService;

    @Transactional
    public SourceResponse create(SourceRequest request, UserPrincipal principal, String ipAddress) {
        String code = request.code().trim().toUpperCase();
        if (sourceRepository.findByCode(code).isPresent()) {
            throw new ConflictException("Source code already exists: " + code);
        }
        RegulationSource source = sourceRepository.save(RegulationSource.builder()
                .code(code)
                .name(request.name().trim())
                .agency(request.agency())
                .baseUrl(request.baseUrl())
                .watchUrl(request.watchUrl())
                .changeDetectionId(request.changeDetectionId())
                .active(request.active() == null || request.active())
                .build());
        auditService.record(principal.email(), principal.role().name(), "SOURCE_CREATED",
                "RegulationSource", source.getId(), "Created source: " + code, ipAddress);
        return toResponse(source);
    }

    @Transactional
    public SourceResponse update(Long id, SourceRequest request, UserPrincipal principal, String ipAddress) {
        RegulationSource source = sourceRepository.findById(id)
                .orElseThrow(() -> new NotFoundException("Source not found: " + id));
        source.setCode(request.code().trim().toUpperCase());
        source.setName(request.name().trim());
        source.setAgency(request.agency());
        source.setBaseUrl(request.baseUrl());
        source.setWatchUrl(request.watchUrl());
        source.setChangeDetectionId(request.changeDetectionId());
        if (request.active() != null) {
            source.setActive(request.active());
        }
        RegulationSource saved = sourceRepository.save(source);
        auditService.record(principal.email(), principal.role().name(), "SOURCE_UPDATED",
                "RegulationSource", saved.getId(), "Updated source: " + saved.getCode(), ipAddress);
        return toResponse(saved);
    }

    @Transactional(readOnly = true)
    public List<SourceResponse> list() {
        return sourceRepository.findAll().stream().map(this::toResponse).toList();
    }

    @Transactional(readOnly = true)
    public SourceResponse get(Long id) {
        return toResponse(sourceRepository.findById(id)
                .orElseThrow(() -> new NotFoundException("Source not found: " + id)));
    }

    private SourceResponse toResponse(RegulationSource source) {
        return new SourceResponse(source.getId(), source.getCode(), source.getName(),
                source.getAgency(), source.getBaseUrl(), source.getWatchUrl(),
                source.getChangeDetectionId(), source.getActive(), source.getCreatedAt());
    }
}
