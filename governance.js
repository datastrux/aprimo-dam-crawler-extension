/**
 * DAM Governance Module
 * 
 * Provides real-time governance capabilities:
 * - Asset expiration monitoring
 * - Duplicate detection
 * - Compliance checking (DAM URL adoption)
 * - SharePoint/Teams notifications
 */

import { encryptedStorage } from './encrypted_storage.js';

// ============================================================================
// Configuration
// ============================================================================

const GOVERNANCE_CONFIG = {
  expiration: {
    warningDays: 30,
    checkIntervalMinutes: 360,  // 6 hours
    alarmName: 'damGovernance_expirationCheck'
  },
  duplicates: {
    enabled: true,
    phashThreshold: 8,  // Hamming distance threshold
    checkOnAssetAdd: true
  },
  compliance: {
    enabled: true,
    damUrlPatterns: [
      /p1\.aprimocdn\.net\/citizensbank\//,  // Current CDN pattern
      /www\.citizensbank\.com\/dam\//         // Future pattern
    ]
  },
  sharepoint: {
    enabled: true,
    authTokenKey: 'sharepointAuthToken',  // Encrypted storage key
    siteUrl: 'https://company.sharepoint.com/sites/DAM',
    endpoints: {
      // Data Layer (Persistent State)
      damAssets: 'https://company.sharepoint.com/sites/DAM/_api/web/lists/getbytitle(\'DAMAssets\')/items',
      discoveredImages: 'https://company.sharepoint.com/sites/DAM/_api/web/lists/getbytitle(\'DiscoveredImages\')/items',
      imageMappings: 'https://company.sharepoint.com/sites/DAM/_api/web/lists/getbytitle(\'ImageMappings\')/items',
      
      // Governance Layer (Events & Monitoring)
      governanceEvents: 'https://company.sharepoint.com/sites/DAM/_api/web/lists/getbytitle(\'GovernanceEvents\')/items',
      
      // Legacy endpoints (deprecated - use governanceEvents instead)
      expirations: 'https://company.sharepoint.com/sites/DAM/_api/web/lists/getbytitle(\'GovernanceEvents\')/items',
      duplicates: 'https://company.sharepoint.com/sites/DAM/_api/web/lists/getbytitle(\'GovernanceEvents\')/items',
      compliance: 'https://company.sharepoint.com/sites/DAM/_api/web/lists/getbytitle(\'GovernanceEvents\')/items'
    },
    teamsWebhook: ''  // Optional: Set to post to Teams channel
  }
};

// ============================================================================
// SharePoint Integration
// ============================================================================

/**
 * Get SharePoint auth token from encrypted storage
 * @returns {Promise<string|null>}
 */
async function getSharePointToken() {
  try {
    const result = await encryptedStorage.get([GOVERNANCE_CONFIG.sharepoint.authTokenKey]);
    return result[GOVERNANCE_CONFIG.sharepoint.authTokenKey] || null;
  } catch (err) {
    console.error('[Governance] Failed to load SharePoint token:', err);
    return null;
  }
}

/**
 * Post data to SharePoint list
 * @param {string} endpoint - SharePoint REST API endpoint
 * @param {Object} data - Payload to post
 * @returns {Promise<Object>}
 */
async function postToSharePoint(endpoint, data) {
  if (!GOVERNANCE_CONFIG.sharepoint.enabled) {
    console.log('[Governance] SharePoint disabled, skipping post');
    return { ok: false, reason: 'disabled' };
  }

  const token = await getSharePointToken();
  if (!token) {
    console.warn('[Governance] No SharePoint token configured');
    return { ok: false, reason: 'no_token' };
  }

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json;odata=verbose',
        'Accept': 'application/json;odata=verbose'
      },
      body: JSON.stringify({ __metadata: { type: 'SP.Data.ListItem' }, ...data })
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('[Governance] SharePoint POST failed:', response.status, errorText);
      return { ok: false, status: response.status, error: errorText };
    }

    const result = await response.json();
    return { ok: true, data: result.d };
  } catch (err) {
    console.error('[Governance] SharePoint POST error:', err);
    return { ok: false, error: String(err?.message || err) };
  }
}

/**
 * Post notification to Teams webhook
 * @param {Object} message - Teams adaptive card or simple message
 * @returns {Promise<Object>}
 */
async function postToTeams(message) {
  if (!GOVERNANCE_CONFIG.sharepoint.teamsWebhook) {
    console.log('[Governance] Teams webhook not configured');
    return { ok: false, reason: 'no_webhook' };
  }

  try {
    const response = await fetch(GOVERNANCE_CONFIG.sharepoint.teamsWebhook, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(message)
    });

    return { ok: response.ok, status: response.status };
  } catch (err) {
    console.error('[Governance] Teams POST error:', err);
    return { ok: false, error: String(err?.message || err) };
  }
}

// ============================================================================
// Data Layer: DAM Assets Sync
// ============================================================================

/**
 * Sync DAM assets to SharePoint DAMAssets list
 * @param {Array} assets - Array of DAM asset objects
 * @returns {Promise<Object>}
 */
async function syncDAMAssets(assets) {
  if (!GOVERNANCE_CONFIG.sharepoint.enabled) {
    return { ok: false, reason: 'disabled' };
  }

  const batchSize = 100;
  let synced = 0;
  let errors = [];

  // Process in batches to avoid timeout
  for (let i = 0; i < assets.length; i += batchSize) {
    const batch = assets.slice(i, i + batchSize);
    
    for (const asset of batch) {
      const payload = {
        Title: asset.fileName || 'Untitled',
        AssetID: asset.itemId,
        FileName: asset.fileName,
        PreviewURL: asset.previewUrl,
        ExpirationDate: asset.expirationDate || null,
        Status: getAssetStatus(asset),
        SHA256: asset.sha256 || '',
        pHash: asset.phash || '',
        FileType: asset.fileType || '',
        LastSyncedFromAprimo: new Date().toISOString()
      };

      try {
        await postToSharePoint(GOVERNANCE_CONFIG.sharepoint.endpoints.damAssets, payload);
        synced++;
      } catch (err) {
        errors.push({ assetId: asset.itemId, error: String(err) });
      }
    }
    
    // Brief pause between batches
    if (i + batchSize < assets.length) {
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }

  return { ok: true, synced, errors, total: assets.length };
}

/**
 * Get asset status based on expiration date
 * @param {Object} asset
 * @returns {string}
 */
function getAssetStatus(asset) {
  if (!asset.expirationDate) return 'Active';
  
  const expDate = new Date(asset.expirationDate);
  const now = new Date();
  const daysUntil = Math.ceil((expDate - now) / (1000 * 60 * 60 * 24));
  
  if (daysUntil < 0) return 'Expired';
  if (daysUntil <= 30) return 'Expiring Soon';
  return 'Active';
}

// ============================================================================
// Data Layer: Discovered Images Sync
// ============================================================================

/**
 * Sync discovered images to SharePoint DiscoveredImages list
 * @param {Array} images - Array of discovered image objects
 * @param {string} discoveredBy - User identifier
 * @returns {Promise<Object>}
 */
async function syncDiscoveredImages(images, discoveredBy = 'Extension User') {
  if (!GOVERNANCE_CONFIG.sharepoint.enabled) {
    return { ok: false, reason: 'disabled' };
  }

  let synced = 0;
  let updated = 0;
  let errors = [];

  for (const img of images) {
    const payload = {
      Title: img.imageUrl || 'Untitled',
      ImageURL: img.imageUrl,
      PageURL: img.pageUrl,
      DiscoveredBy: discoveredBy,
      LastSeen: new Date().toISOString(),
      Status: 'Active',
      ImageAlt: img.imageAlt || ''
    };

    try {
      // TODO: Check if image already exists and update LastSeen instead of creating duplicate
      await postToSharePoint(GOVERNANCE_CONFIG.sharepoint.endpoints.discoveredImages, payload);
      synced++;
    } catch (err) {
      errors.push({ imageUrl: img.imageUrl, error: String(err) });
    }
  }

  return { ok: true, synced, updated, errors };
}

// ============================================================================
// Data Layer: Image Mappings
// ============================================================================

/**
 * Create image mapping in SharePoint ImageMappings list
 * @param {Object} mapping - Mapping details
 * @returns {Promise<Object>}
 */
async function createImageMapping(mapping) {
  const payload = {
    Title: `${mapping.imageUrl} → ${mapping.damAssetId}`,
    CitizensBankImageURL: mapping.imageUrl,
    DAMAssetID: mapping.damAssetId,
    MatchConfidence: mapping.confidence || 100,
    MatchMethod: mapping.method || 'Unknown',
    IsDuplicate: mapping.isDuplicate || false,
    LastVerified: new Date().toISOString()
  };

  return await postToSharePoint(
    GOVERNANCE_CONFIG.sharepoint.endpoints.imageMappings,
    payload
  );
}

// ============================================================================
// Governance Layer: Unified Events
// ============================================================================

/**
 * Post a governance event to SharePoint GovernanceEvents list
 * @param {Object} event - Event details
 * @returns {Promise<Object>}
 */
async function postGovernanceEvent(event) {
  const payload = {
    Title: event.title || 'Governance Event',
    EventType: event.eventType,  // ExpirationReport, DuplicateDetected, ComplianceViolation, etc.
    EventDate: new Date().toISOString(),
    EventData: JSON.stringify(event.data || {}),
    Severity: event.severity || 'Medium',  // Low, Medium, High, Critical
    NotificationSent: event.notificationSent || false,
    AssignedTo: event.assignedTo || null,
    Status: event.status || 'New'  // New, InProgress, Resolved
  };

  return await postToSharePoint(
    GOVERNANCE_CONFIG.sharepoint.endpoints.governanceEvents,
    payload
  );
}

// ============================================================================
// Expiration Monitoring
// ============================================================================

/**
 * Check for expiring/expired assets and post notifications
 * @param {Object} assets - Asset dictionary from content.js state
 * @returns {Promise<Object>}
 */
async function checkExpirations(assets) {
  const now = new Date();
  const expired = [];
  const expiringSoon = [];

  for (const asset of Object.values(assets || {})) {
    if (!asset?.expirationDate) continue;

    try {
      const expDate = new Date(asset.expirationDate);
      if (isNaN(expDate.getTime())) continue;

      const daysUntil = Math.ceil((expDate - now) / (1000 * 60 * 60 * 24));

      if (daysUntil < 0) {
        expired.push({
          itemId: asset.itemId,
          fileName: asset.fileName,
          itemUrl: asset.itemUrl,
          expirationDate: asset.expirationDate,
          daysExpired: Math.abs(daysUntil),
          status: asset.status
        });
      } else if (daysUntil <= GOVERNANCE_CONFIG.expiration.warningDays) {
        expiringSoon.push({
          itemId: asset.itemId,
          fileName: asset.fileName,
          itemUrl: asset.itemUrl,
          expirationDate: asset.expirationDate,
          daysRemaining: daysUntil,
          status: asset.status
        });
      }
    } catch {
      continue;
    }
  }

  console.log(`[Governance] Expiration check: ${expired.length} expired, ${expiringSoon.length} expiring soon`);

  // Post to SharePoint if any issues found
  if (expired.length > 0 || expiringSoon.length > 0) {
    const spResult = await postGovernanceEvent({
      title: `Asset Expiration Report - ${expired.length} expired, ${expiringSoon.length} expiring soon`,
      eventType: 'ExpirationReport',
      severity: expired.length > 0 ? 'High' : 'Medium',
      data: {
        expiredCount: expired.length,
        expiringSoonCount: expiringSoon.length,
        expired,
        expiringSoon
      }
    });

    // Also post to Teams if configured
    if (GOVERNANCE_CONFIG.sharepoint.teamsWebhook) {
      const teamsMessage = {
        '@type': 'MessageCard',
        '@context': 'https://schema.org/extensions',
        summary: `DAM Asset Expiration Alert`,
        themeColor: expired.length > 0 ? 'FF0000' : 'FFA500',
        title: '⚠️ DAM Asset Expiration Alert',
        sections: [{
          facts: [
            { name: 'Expired Assets', value: String(expired.length) },
            { name: 'Expiring Soon (30 days)', value: String(expiringSoon.length) }
          ],
          text: `${expired.length} assets have expired and ${expiringSoon.length} are expiring within ${GOVERNANCE_CONFIG.expiration.warningDays} days.`
        }]
      };

      await postToTeams(teamsMessage);
    }

    return { ok: true, expired, expiringSoon, posted: spResult.ok };
  }

  return { ok: true, expired: [], expiringSoon: [], posted: false };
}

// ============================================================================
// Duplicate Detection
// ============================================================================

/**
 * Check if a new asset is a potential duplicate
 * @param {Object} asset - New asset to check
 * @param {Object} existingAssets - Dictionary of existing assets
 * @returns {Array} - Array of potential duplicate matches
 */
function detectDuplicates(asset, existingAssets) {
  if (!GOVERNANCE_CONFIG.duplicates.enabled) return [];

  const duplicates = [];

  // SHA256 exact match (pixel-perfect duplicate)
  if (asset.sha256) {
    for (const existing of Object.values(existingAssets)) {
      if (existing.itemId === asset.itemId) continue;  // Skip self
      if (existing.sha256 === asset.sha256) {
        duplicates.push({
          type: 'exact',
          matchedAsset: {
            itemId: existing.itemId,
            fileName: existing.fileName,
            sha256: existing.sha256
          },
          confidence: 1.0
        });
      }
    }
  }

  // pHash perceptual match (visually similar)
  if (asset.phash) {
    for (const existing of Object.values(existingAssets)) {
      if (existing.itemId === asset.itemId) continue;
      if (!existing.phash) continue;

      const distance = hammingDistance(asset.phash, existing.phash);
      if (distance <= GOVERNANCE_CONFIG.duplicates.phashThreshold) {
        duplicates.push({
          type: 'perceptual',
          matchedAsset: {
            itemId: existing.itemId,
            fileName: existing.fileName,
            phash: existing.phash
          },
          distance,
          confidence: 1 - (distance / 64)  // Normalized confidence score
        });
      }
    }
  }

  return duplicates;
}

/**
 * Calculate Hamming distance between two hex-encoded hashes
 * @param {string} hash1 - First hash (hex string)
 * @param {string} hash2 - Second hash (hex string)
 * @returns {number} - Hamming distance (0-64 for 64-bit hashes)
 */
function hammingDistance(hash1, hash2) {
  if (!hash1 || !hash2 || hash1.length !== hash2.length) return 999;

  let distance = 0;
  for (let i = 0; i < hash1.length; i++) {
    const xor = parseInt(hash1[i], 16) ^ parseInt(hash2[i], 16);
    // Count bits in XOR result
    distance += xor.toString(2).split('1').length - 1;
  }
  return distance;
}

/**
 * Post duplicate notification to SharePoint
 * @param {Object} asset - The new asset
 * @param {Array} duplicates - Array of duplicate matches
 * @returns {Promise<Object>}
 */
async function notifyDuplicateDetection(asset, duplicates) {
  if (duplicates.length === 0) return { ok: true, posted: false };

  console.log(`[Governance] Duplicate detected: ${asset.fileName} has ${duplicates.length} matches`);

  const highestConfidence = Math.max(...duplicates.map(d => d.confidence));
  const hasExactMatch = duplicates.some(d => d.type === 'exact');

  const result = await postGovernanceEvent({
    title: `Duplicate Detected: ${asset.fileName}`,
    eventType: 'DuplicateDetected',
    severity: hasExactMatch ? 'High' : 'Medium',
    data: {
      newAssetId: asset.itemId,
      newAssetFileName: asset.fileName,
      newAssetUrl: asset.itemUrl,
      duplicateCount: duplicates.length,
      duplicateMatches: duplicates,
      highestConfidence
    }
  });

  // Post to Teams for high-confidence duplicates
  if (duplicates.some(d => d.type === 'exact')) {
    const teamsMessage = {
      '@type': 'MessageCard',
      '@context': 'https://schema.org/extensions',
      summary: 'Duplicate Asset Detected',
      themeColor: 'FFA500',
      title: '🔍 Duplicate Asset Detected',
      sections: [{
        facts: [
          { name: 'New Asset', value: asset.fileName },
          { name: 'Asset ID', value: asset.itemId },
          { name: 'Duplicates Found', value: String(duplicates.length) },
          { name: 'Match Type', value: duplicates[0].type }
        ]
      }]
    };

    await postToTeams(teamsMessage);
  }

  return { ok: true, posted: result.ok, duplicates };
}

// ============================================================================
// Compliance Checking
// ============================================================================

/**
 * Check if a URL is using DAM CDN vs local copy
 * @param {string} url - Image URL to check
 * @returns {Object} - {isCompliant, urlType, pattern}
 */
function checkUrlCompliance(url) {
  if (!url || !GOVERNANCE_CONFIG.compliance.enabled) {
    return { isCompliant: null, urlType: 'unknown', pattern: null };
  }

  for (const pattern of GOVERNANCE_CONFIG.compliance.damUrlPatterns) {
    if (pattern.test(url)) {
      return { isCompliant: true, urlType: 'dam_cdn', pattern: pattern.source };
    }
  }

  return { isCompliant: false, urlType: 'local_copy', pattern: null };
}

/**
 * Post compliance issue to SharePoint
 * @param {Object} issue - Compliance issue details
 * @returns {Promise<Object>}
 */
async function notifyComplianceIssue(issue) {
  console.log('[Governance] Compliance issue:', issue.imageUrl);

  return await postGovernanceEvent({
    title: `Non-DAM URL Detected: ${issue.pageUrl}`,
    eventType: 'ComplianceViolation',
    severity: issue.severity || 'Medium',  // Can be set based on image importance
    data: {
      pageUrl: issue.pageUrl,
      imageUrl: issue.imageUrl,
      imageAlt: issue.imageAlt || '',
      expected: 'DAM CDN URL',
      actual: 'Local copy'
    }
  });
}

// ============================================================================
// Public API
// ============================================================================

export const governance = {
  // Data Layer - Persistent State
  syncDAMAssets,
  syncDiscoveredImages,
  createImageMapping,
  
  // Governance Layer - Events & Monitoring
  postGovernanceEvent,
  checkExpirations,
  detectDuplicates,
  notifyDuplicateDetection,
  checkUrlCompliance,
  notifyComplianceIssue,
  
  // SharePoint Integration
  getSharePointToken,
  postToSharePoint,
  postToTeams,
  
  // Configuration Access
  config: GOVERNANCE_CONFIG
};

// ============================================================================
// Global Console Helpers
// ============================================================================

/**
 * Store SharePoint auth token in encrypted storage
 * Usage: await storeSharePointToken('YOUR_BEARER_TOKEN')
 */
globalThis.storeSharePointToken = async function(token) {
  try {
    await encryptedStorage.set({ [GOVERNANCE_CONFIG.sharepoint.authTokenKey]: token });
    console.log('✅ SharePoint token stored in encrypted storage');
    return true;
  } catch (err) {
    console.error('❌ Failed to store SharePoint token:', err);
    return false;
  }
};

/**
 * Check if SharePoint token is configured
 * Usage: await checkSharePointToken()
 */
globalThis.checkSharePointToken = async function() {
  const token = await getSharePointToken();
  if (token) {
    console.log('✅ SharePoint token is configured');
    console.log('Token (first 20 chars):', token.substring(0, 20) + '...');
    return true;
  } else {
    console.log('❌ No SharePoint token configured');
    console.log('Run: await storeSharePointToken("YOUR_BEARER_TOKEN")');
    return false;
  }
};
