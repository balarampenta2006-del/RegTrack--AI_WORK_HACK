package com.regtrack.backend.service;

import com.regtrack.backend.dto.DiffDtos.*;
import com.regtrack.backend.model.Regulation;
import com.regtrack.backend.model.RegulationVersion;
import com.regtrack.backend.repository.RegulationRepository;
import com.regtrack.backend.repository.RegulationVersionRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class DiffServiceTest {

    @Mock
    private RegulationRepository regulationRepository;

    @Mock
    private RegulationVersionRepository versionRepository;

    @InjectMocks
    private DiffService diffService;

    private Regulation testRegulation;
    private RegulationVersion version1;
    private RegulationVersion version2;

    @BeforeEach
    void setUp() {
        testRegulation = Regulation.builder()
                .id(100L)
                .title("RBI Master Direction on Cyber Security")
                .url("https://rbi.org.in/master-direction")
                .category("BANKING")
                .build();

        version1 = RegulationVersion.builder()
                .id(1L)
                .regulationId(100L)
                .versionNo(1)
                .content("""
                        # Section 1: Overview
                        All regulated entities must maintain baseline cyber security controls.
                        Compliance deadline is 31/12/2025.
                        Penalty for non-compliance is ₹5,00,000.
                        """)
                .contentHash("hash1")
                .fetchedAt(LocalDateTime.now().minusDays(10))
                .current(false)
                .build();

        version2 = RegulationVersion.builder()
                .id(2L)
                .regulationId(100L)
                .versionNo(2)
                .content("""
                        # Section 1: Overview
                        All regulated entities SHALL maintain advanced cyber security controls.
                        Compliance deadline is 30/06/2026.
                        Penalty for non-compliance is ₹10,00,000.
                        
                        # Section 2: Incident Reporting
                        Mandatory reporting within 6 hours.
                        """)
                .contentHash("hash2")
                .fetchedAt(LocalDateTime.now())
                .current(true)
                .build();
    }

    @Test
    void compareVersions_ShouldCalculateDiffStatsAndMetrics() {
        when(regulationRepository.findById(100L)).thenReturn(Optional.of(testRegulation));
        when(versionRepository.findByRegulationIdOrderByVersionNoDesc(100L)).thenReturn(List.of(version2, version1));

        VersionDiffResponse result = diffService.compareVersions(100L, 1, 2);

        assertNotNull(result);
        assertEquals(100L, result.regulationId());
        assertEquals("RBI Master Direction on Cyber Security", result.regulationTitle());
        assertEquals(1, result.oldVersionNo());
        assertEquals(2, result.newVersionNo());

        // Line diffs check
        assertFalse(result.lineDiffs().isEmpty());

        // Clause diffs check (Section 1 modified, Section 2 added)
        assertFalse(result.clauseDiffs().isEmpty());
        assertTrue(result.clauseDiffs().stream().anyMatch(c -> c.clauseHeader().contains("Section 2") && c.changeType() == ClauseChangeType.ADDED));

        // Metric changes check (dates, monetary penalties, keywords)
        assertFalse(result.metricChanges().isEmpty());
        assertTrue(result.metricChanges().stream().anyMatch(m -> m.newValue() != null && m.newValue().contains("₹10,00,000")));
        assertTrue(result.metricChanges().stream().anyMatch(m -> m.newValue() != null && m.newValue().equals("SHALL")));

        // Unified patch check
        assertNotNull(result.unifiedPatch());
        assertTrue(result.unifiedPatch().contains("--- RBI Master Direction on Cyber Security (Version 1)"));
        assertTrue(result.unifiedPatch().contains("+++ RBI Master Direction on Cyber Security (Version 2)"));
    }

    @Test
    void getVersions_ShouldReturnVersionSummaries() {
        when(regulationRepository.findById(100L)).thenReturn(Optional.of(testRegulation));
        when(versionRepository.findByRegulationIdOrderByVersionNoDesc(100L)).thenReturn(List.of(version2, version1));

        List<VersionSummaryDto> summaries = diffService.getVersions(100L);

        assertEquals(2, summaries.size());
        assertEquals(2, summaries.get(0).versionNo());
        assertEquals(1, summaries.get(1).versionNo());
    }
}
