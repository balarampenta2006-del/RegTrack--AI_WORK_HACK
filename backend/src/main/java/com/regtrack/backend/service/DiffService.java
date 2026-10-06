package com.regtrack.backend.service;

import com.regtrack.backend.dto.DiffDtos.*;
import com.regtrack.backend.exception.NotFoundException;
import com.regtrack.backend.model.Regulation;
import com.regtrack.backend.model.RegulationVersion;
import com.regtrack.backend.repository.RegulationRepository;
import com.regtrack.backend.repository.RegulationVersionRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Service
@RequiredArgsConstructor
@Slf4j
public class DiffService {

    private final RegulationRepository regulationRepository;
    private final RegulationVersionRepository versionRepository;

    private static final Pattern NUMERIC_PATTERN = Pattern.compile("(?:\\b\\d+(?:\\.\\d+)?%|(?:₹|\\$|\\b(?:EUR|INR|Rs\\.?))\\s*\\d+(?:,\\d+)*(?:\\.\\d+)?|\\b\\d+(?:\\.\\d+)?\\s*(?:percent|percentage|days|months|years|basis points|bps)\\b)", Pattern.CASE_INSENSITIVE);
    private static final Pattern DATE_PATTERN = Pattern.compile("\\b(?:\\d{1,2}[/-]\\d{1,2}[/-]\\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \\d{1,2},? \\d{4}|by \\d{1,2}(?:st|nd|rd|th)? [A-Za-z]+ \\d{4})\\b", Pattern.CASE_INSENSITIVE);
    private static final Pattern KEYWORD_PATTERN = Pattern.compile("\\b(SHALL|MUST|PROHIBITED|MANDATORY|PENALTY|SANCTION|REQUIREMENT|COMPLIANCE|RESTRICTION|EXEMPTION)\\b", Pattern.CASE_INSENSITIVE);

    @Transactional(readOnly = true)
    public List<VersionSummaryDto> getVersions(Long regulationId) {
        getRegulation(regulationId); // validate existence
        return versionRepository.findByRegulationIdOrderByVersionNoDesc(regulationId)
                .stream()
                .map(this::toSummaryDto)
                .toList();
    }

    @Transactional(readOnly = true)
    public RegulationVersion getVersion(Long regulationId, Integer versionNo) {
        return versionRepository.findByRegulationIdAndVersionNo(regulationId, versionNo)
                .orElseThrow(() -> new NotFoundException("Version " + versionNo + " not found for regulation " + regulationId));
    }

    @Transactional(readOnly = true)
    public VersionDiffResponse compareVersions(Long regulationId, Integer oldVersionNo, Integer newVersionNo) {
        Regulation regulation = getRegulation(regulationId);
        List<RegulationVersion> versions = versionRepository.findByRegulationIdOrderByVersionNoDesc(regulationId);

        if (versions.isEmpty()) {
            throw new NotFoundException("No versions found for regulation " + regulationId);
        }

        RegulationVersion oldVersion;
        RegulationVersion newVersion;

        if (oldVersionNo != null && newVersionNo != null) {
            oldVersion = findVersionByNumber(versions, oldVersionNo);
            newVersion = findVersionByNumber(versions, newVersionNo);
        } else if (versions.size() >= 2) {
            newVersion = versions.get(0); // latest
            oldVersion = versions.get(1); // previous
        } else {
            // Only 1 version exists
            newVersion = versions.get(0);
            oldVersion = versions.get(0);
        }

        String oldText = oldVersion.getContent() != null ? oldVersion.getContent() : "";
        String newText = newVersion.getContent() != null ? newVersion.getContent() : "";

        String[] oldLines = oldText.isBlank() ? new String[0] : oldText.split("\\r?\\n");
        String[] newLines = newText.isBlank() ? new String[0] : newText.split("\\r?\\n");

        List<DiffLineDto> lineDiffs = computeLineDiffs(oldLines, newLines);
        DiffStatsDto stats = computeStats(oldLines.length, newLines.length, lineDiffs);
        List<ClauseDiffDto> clauseDiffs = computeClauseDiffs(oldText, newText);
        List<MetricChangeDto> metricChanges = computeMetricChanges(oldText, newText);
        String unifiedPatch = generateUnifiedPatch(regulation.getTitle(), oldVersion.getVersionNo(), newVersion.getVersionNo(), lineDiffs);

        return new VersionDiffResponse(
                regulationId,
                regulation.getTitle(),
                oldVersion.getVersionNo(),
                newVersion.getVersionNo(),
                oldVersion.getId(),
                newVersion.getId(),
                stats,
                lineDiffs,
                clauseDiffs,
                metricChanges,
                unifiedPatch,
                LocalDateTime.now()
        );
    }

    private Regulation getRegulation(Long id) {
        return regulationRepository.findById(id)
                .orElseThrow(() -> new NotFoundException("Regulation not found with id: " + id));
    }

    private RegulationVersion findVersionByNumber(List<RegulationVersion> versions, int versionNo) {
        return versions.stream()
                .filter(v -> v.getVersionNo() == versionNo)
                .findFirst()
                .orElseThrow(() -> new NotFoundException("Version number " + versionNo + " not found"));
    }

    private VersionSummaryDto toSummaryDto(RegulationVersion v) {
        return new VersionSummaryDto(
                v.getId(),
                v.getRegulationId(),
                v.getVersionNo(),
                v.getContentHash(),
                v.getSourceUrl(),
                v.getFetchedAt(),
                v.getCurrent(),
                v.getContent() != null ? v.getContent().length() : 0
        );
    }

    /**
     * Compute line diff using Longest Common Subsequence (LCS).
     */
    private List<DiffLineDto> computeLineDiffs(String[] oldLines, String[] newLines) {
        int m = oldLines.length;
        int n = newLines.length;

        int[][] lcs = new int[m + 1][n + 1];
        for (int i = 0; i < m; i++) {
            for (int j = 0; j < n; j++) {
                if (oldLines[i].trim().equals(newLines[j].trim())) {
                    lcs[i + 1][j + 1] = lcs[i][j] + 1;
                } else {
                    lcs[i + 1][j + 1] = Math.max(lcs[i + 1][j], lcs[i][j + 1]);
                }
            }
        }

        List<DiffLineDto> result = new ArrayList<>();
        int i = m, j = n;
        Stack<DiffLineDto> stack = new Stack<>();

        while (i > 0 || j > 0) {
            if (i > 0 && j > 0 && oldLines[i - 1].trim().equals(newLines[j - 1].trim())) {
                stack.push(new DiffLineDto(i, j, DiffType.EQUAL, oldLines[i - 1]));
                i--;
                j--;
            } else if (j > 0 && (i == 0 || lcs[i][j - 1] >= lcs[i - 1][j])) {
                stack.push(new DiffLineDto(null, j, DiffType.ADD, newLines[j - 1]));
                j--;
            } else if (i > 0 && (j == 0 || lcs[i][j - 1] < lcs[i - 1][j])) {
                stack.push(new DiffLineDto(i, null, DiffType.DELETE, oldLines[i - 1]));
                i--;
            }
        }

        while (!stack.isEmpty()) {
            result.add(stack.pop());
        }

        return result;
    }

    private DiffStatsDto computeStats(int totalOld, int totalNew, List<DiffLineDto> diffs) {
        int additions = 0;
        int deletions = 0;
        int equal = 0;

        for (DiffLineDto d : diffs) {
            if (d.type() == DiffType.ADD) additions++;
            else if (d.type() == DiffType.DELETE) deletions++;
            else if (d.type() == DiffType.EQUAL) equal++;
        }

        int totalChanges = additions + deletions;
        double totalLines = Math.max(totalOld, totalNew);
        double similarity = totalLines == 0 ? 100.0 : Math.max(0.0, Math.round(((totalLines - (totalChanges / 2.0)) / totalLines) * 10000.0) / 100.0);

        return new DiffStatsDto(totalOld, totalNew, additions, deletions, 0, equal, similarity);
    }

    /**
     * Compute clause/section level diffs based on Markdown headings (# Section) or numbered clauses.
     */
    private List<ClauseDiffDto> computeClauseDiffs(String oldText, String newText) {
        Map<String, String> oldClauses = extractClauses(oldText);
        Map<String, String> newClauses = extractClauses(newText);

        List<ClauseDiffDto> clauseDiffs = new ArrayList<>();
        Set<String> allHeaders = new LinkedHashSet<>(oldClauses.keySet());
        allHeaders.addAll(newClauses.keySet());

        for (String header : allHeaders) {
            String oldContent = oldClauses.get(header);
            String newContent = newClauses.get(header);

            if (oldContent == null) {
                clauseDiffs.add(new ClauseDiffDto(header, ClauseChangeType.ADDED, null, newContent, "New section added"));
            } else if (newContent == null) {
                clauseDiffs.add(new ClauseDiffDto(header, ClauseChangeType.DELETED, oldContent, null, "Section removed"));
            } else if (!oldContent.trim().equals(newContent.trim())) {
                clauseDiffs.add(new ClauseDiffDto(header, ClauseChangeType.MODIFIED, oldContent, newContent, "Content updated"));
            } else {
                clauseDiffs.add(new ClauseDiffDto(header, ClauseChangeType.UNCHANGED, oldContent, newContent, "No changes"));
            }
        }

        return clauseDiffs;
    }

    private Map<String, String> extractClauses(String text) {
        Map<String, String> clauses = new LinkedHashMap<>();
        if (text == null || text.isBlank()) return clauses;

        String[] lines = text.split("\\r?\\n");
        String currentHeader = "Preamble / General";
        StringBuilder currentBody = new StringBuilder();

        for (String line : lines) {
            if (line.startsWith("#") || line.matches("(?i)^(Section|Clause|Article|Paragraph|Rule)\\s+\\d+.*")) {
                if (currentBody.length() > 0) {
                    clauses.put(currentHeader, currentBody.toString().trim());
                    currentBody.setLength(0);
                }
                currentHeader = line.replaceAll("^#+\\s*", "").trim();
            } else {
                currentBody.append(line).append("\n");
            }
        }
        if (currentBody.length() > 0) {
            clauses.put(currentHeader, currentBody.toString().trim());
        }
        return clauses;
    }

    /**
     * Compute key metric and regulatory term changes between versions.
     */
    private List<MetricChangeDto> computeMetricChanges(String oldText, String newText) {
        List<MetricChangeDto> metrics = new ArrayList<>();

        // Extract numbers / percentages
        extractMetricPairs(oldText, newText, NUMERIC_PATTERN, MetricType.NUMERIC_VALUE, "Financial/Numerical Value Shift", metrics);

        // Extract dates / deadlines
        extractMetricPairs(oldText, newText, DATE_PATTERN, MetricType.DEADLINE, "Compliance Deadline Change", metrics);

        // Extract regulatory terms
        extractMetricPairs(oldText, newText, KEYWORD_PATTERN, MetricType.COMPLIANCE_KEYWORD, "Mandatory Regulatory Keyword Added/Changed", metrics);

        return metrics;
    }

    private void extractMetricPairs(String oldText, String newText, Pattern pattern, MetricType type, String desc, List<MetricChangeDto> results) {
        Set<String> oldMatches = findMatches(oldText, pattern);
        Set<String> newMatches = findMatches(newText, pattern);

        Set<String> added = new HashSet<>(newMatches);
        added.removeAll(oldMatches);

        Set<String> removed = new HashSet<>(oldMatches);
        removed.removeAll(newMatches);

        for (String val : added) {
            String context = extractContext(newText, val);
            results.add(new MetricChangeDto(type, desc, null, val, context));
        }

        for (String val : removed) {
            String context = extractContext(oldText, val);
            results.add(new MetricChangeDto(type, desc, val, null, context));
        }
    }

    private Set<String> findMatches(String text, Pattern pattern) {
        Set<String> matches = new LinkedHashSet<>();
        if (text == null) return matches;
        Matcher m = pattern.matcher(text);
        while (m.find()) {
            matches.add(m.group());
        }
        return matches;
    }

    private String extractContext(String text, String target) {
        if (text == null || target == null) return "";
        int idx = text.indexOf(target);
        if (idx == -1) return target;
        int start = Math.max(0, idx - 40);
        int end = Math.min(text.length(), idx + target.length() + 40);
        return "..." + text.substring(start, end).replaceAll("\\r?\\n", " ") + "...";
    }

    private String generateUnifiedPatch(String title, int v1, int v2, List<DiffLineDto> lineDiffs) {
        StringBuilder patch = new StringBuilder();
        patch.append("--- ").append(title).append(" (Version ").append(v1).append(")\n");
        patch.append("+++ ").append(title).append(" (Version ").append(v2).append(")\n");
        patch.append("@@ -1,").append(lineDiffs.size()).append(" +1,").append(lineDiffs.size()).append(" @@\n");

        for (DiffLineDto line : lineDiffs) {
            switch (line.type()) {
                case ADD -> patch.append("+").append(line.text()).append("\n");
                case DELETE -> patch.append("-").append(line.text()).append("\n");
                case EQUAL -> patch.append(" ").append(line.text()).append("\n");
                default -> patch.append(" ").append(line.text()).append("\n");
            }
        }
        return patch.toString();
    }
}
