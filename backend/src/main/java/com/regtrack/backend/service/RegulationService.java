package com.regtrack.backend.service;

import com.regtrack.backend.dto.RegulationDtos.RegulationResponse;
import com.regtrack.backend.dto.RegulationDtos.VersionDetailResponse;
import com.regtrack.backend.dto.RegulationDtos.VersionSummaryResponse;
import com.regtrack.backend.exception.NotFoundException;
import com.regtrack.backend.model.Regulation;
import com.regtrack.backend.model.RegulationSource;
import com.regtrack.backend.model.RegulationVersion;
import com.regtrack.backend.repository.RegulationRepository;
import com.regtrack.backend.repository.RegulationSourceRepository;
import com.regtrack.backend.repository.RegulationVersionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
public class RegulationService {

    private final RegulationRepository regulationRepository;
    private final RegulationVersionRepository versionRepository;
    private final RegulationSourceRepository sourceRepository;

    @Transactional(readOnly = true)
    public List<RegulationResponse> list(String sourceCode) {
        List<Regulation> regulations;
        if (sourceCode != null && !sourceCode.isBlank()) {
            RegulationSource source = sourceRepository.findByCode(sourceCode.trim().toUpperCase())
                    .orElseThrow(() -> new NotFoundException("Source not found: " + sourceCode));
            regulations = regulationRepository.findBySourceIdOrderByCreatedAtDesc(source.getId());
        } else {
            regulations = regulationRepository.findAll();
        }
        return regulations.stream().map(this::toResponse).toList();
    }

    @Transactional(readOnly = true)
    public RegulationResponse get(Long id) {
        return toResponse(load(id));
    }

    @Transactional(readOnly = true)
    public List<VersionSummaryResponse> listVersions(Long regulationId) {
        load(regulationId);
        return versionRepository.findByRegulationIdOrderByVersionNoDesc(regulationId).stream()
                .map(this::toSummary)
                .toList();
    }

    @Transactional(readOnly = true)
    public VersionDetailResponse getVersion(Long regulationId, Long versionId) {
        load(regulationId);
        RegulationVersion version = versionRepository.findById(versionId)
                .orElseThrow(() -> new NotFoundException("Version not found: " + versionId));
        if (!version.getRegulationId().equals(regulationId)) {
            throw new NotFoundException("Version " + versionId + " does not belong to regulation " + regulationId);
        }
        return new VersionDetailResponse(version.getId(), version.getRegulationId(), version.getVersionNo(),
                version.getContent(), version.getContentHash(), version.getStoragePath(),
                version.getSourceUrl(), version.getFetchedAt(), version.getCurrent());
    }

    private Regulation load(Long id) {
        return regulationRepository.findById(id)
                .orElseThrow(() -> new NotFoundException("Regulation not found: " + id));
    }

    private RegulationResponse toResponse(Regulation regulation) {
        String sourceCode = sourceRepository.findById(regulation.getSourceId())
                .map(RegulationSource::getCode)
                .orElse(null);
        long versionCount = versionRepository.countByRegulationId(regulation.getId());
        Long currentVersionId = versionRepository.findFirstByRegulationIdAndCurrentTrue(regulation.getId())
                .map(RegulationVersion::getId)
                .orElse(null);
        return new RegulationResponse(
                regulation.getId(), regulation.getSourceId(), sourceCode,
                regulation.getTitle(), regulation.getIdentifier(), regulation.getUrl(),
                regulation.getCategory(), regulation.getPublishedDate(), regulation.getEffectiveDate(),
                (int) versionCount, currentVersionId, regulation.getCreatedAt());
    }

    private VersionSummaryResponse toSummary(RegulationVersion version) {
        return new VersionSummaryResponse(version.getId(), version.getRegulationId(),
                version.getVersionNo(), version.getContentHash(), version.getSourceUrl(),
                version.getFetchedAt(), version.getCurrent());
    }
}
