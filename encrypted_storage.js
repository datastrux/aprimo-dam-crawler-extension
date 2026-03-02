// Encrypted storage wrapper using Web Crypto API
// Provides transparent encryption for sensitive data in chrome.storage.local

const ENCRYPTED_STORAGE_VERSION = 1;

/**
 * Derive encryption key from user's secret or generate new one
 * @returns {Promise<CryptoKey>}
 */
async function deriveEncryptionKey() {
  // Check if we have a stored key ID
  const result = await chrome.storage.local.get(['_encryptionKeyId']);
  let keyMaterial;

  if (result._encryptionKeyId) {
    // Use existing key ID as seed
    keyMaterial = result._encryptionKeyId;
  } else {
    // Generate new random key ID
    const randomBytes = crypto.getRandomValues(new Uint8Array(32));
    keyMaterial = Array.from(randomBytes).map(b => b.toString(16).padStart(2, '0')).join('');
    await chrome.storage.local.set({ _encryptionKeyId: keyMaterial });
  }

  // Derive AES-GCM key from key material
  const encoder = new TextEncoder();
  const keyMaterialBytes = encoder.encode(keyMaterial);
  
  const importedKey = await crypto.subtle.importKey(
    'raw',
    keyMaterialBytes,
    'PBKDF2',
    false,
    ['deriveBits', 'deriveKey']
  );

  return await crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt: encoder.encode('aprimo-dam-audit-salt-v1'),
      iterations: 100000,
      hash: 'SHA-256'
    },
    importedKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt']
  );
}

/**
 * Encrypt data using AES-GCM
 * @param {any} data - Data to encrypt (will be JSON stringified)
 * @param {CryptoKey} key - Encryption key
 * @returns {Promise<Object>} Encrypted payload with IV and ciphertext
 */
async function encryptData(data, key) {
  const encoder = new TextEncoder();
  const plaintext = encoder.encode(JSON.stringify(data));
  
  // Generate random IV (12 bytes for GCM)
  const iv = crypto.getRandomValues(new Uint8Array(12));
  
  // Encrypt
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    plaintext
  );

  return {
    version: ENCRYPTED_STORAGE_VERSION,
    iv: Array.from(iv).map(b => b.toString(16).padStart(2, '0')).join(''),
    data: Array.from(new Uint8Array(ciphertext)).map(b => b.toString(16).padStart(2, '0')).join('')
  };
}

/**
 * Decrypt data using AES-GCM
 * @param {Object} encryptedPayload - Encrypted payload with IV and ciphertext
 * @param {CryptoKey} key - Decryption key
 * @returns {Promise<any>} Decrypted data
 */
async function decryptData(encryptedPayload, key) {
  if (encryptedPayload.version !== ENCRYPTED_STORAGE_VERSION) {
    throw new Error(`Unsupported encryption version: ${encryptedPayload.version}`);
  }

  // Convert hex strings back to Uint8Array
  const iv = new Uint8Array(encryptedPayload.iv.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));
  const ciphertext = new Uint8Array(encryptedPayload.data.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));

  // Decrypt
  const plaintext = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv },
    key,
    ciphertext
  );

  const decoder = new TextDecoder();
  return JSON.parse(decoder.decode(plaintext));
}

/**
 * Encrypted storage wrapper
 */
class EncryptedStorage {
  constructor() {
    this._key = null;
    this._ready = false;
  }

  /**
   * Initialize encryption key (must be called before use)
   */
  async init() {
    if (this._ready) return;
    this._key = await deriveEncryptionKey();
    this._ready = true;
  }

  /**
   * Store encrypted data
   * @param {Object} items - Key-value pairs to encrypt and store
   */
  async set(items) {
    if (!this._ready) await this.init();

    const encryptedItems = {};
    for (const [key, value] of Object.entries(items)) {
      const encrypted = await encryptData(value, this._key);
      encryptedItems[`_enc_${key}`] = encrypted;
    }

    return new Promise((resolve, reject) => {
      chrome.storage.local.set(encryptedItems, () => {
        if (chrome.runtime.lastError) {
          reject(chrome.runtime.lastError);
        } else {
          resolve();
        }
      });
    });
  }

  /**
   * Retrieve and decrypt data
   * @param {string[]} keys - Keys to retrieve
   * @returns {Promise<Object>} Decrypted key-value pairs
   */
  async get(keys) {
    if (!this._ready) await this.init();

    const encryptedKeys = keys.map(k => `_enc_${k}`);
    
    return new Promise((resolve, reject) => {
      chrome.storage.local.get(encryptedKeys, async (result) => {
        if (chrome.runtime.lastError) {
          reject(chrome.runtime.lastError);
          return;
        }

        const decrypted = {};
        for (const key of keys) {
          const encKey = `_enc_${key}`;
          if (result[encKey]) {
            try {
              decrypted[key] = await decryptData(result[encKey], this._key);
            } catch (err) {
              console.error(`[EncryptedStorage] Failed to decrypt ${key}:`, err);
              decrypted[key] = null;
            }
          }
        }
        resolve(decrypted);
      });
    });
  }

  /**
   * Remove encrypted data
   * @param {string[]} keys - Keys to remove
   */
  async remove(keys) {
    const encryptedKeys = keys.map(k => `_enc_${k}`);
    return new Promise((resolve, reject) => {
      chrome.storage.local.remove(encryptedKeys, () => {
        if (chrome.runtime.lastError) {
          reject(chrome.runtime.lastError);
        } else {
          resolve();
        }
      });
    });
  }

  /**
   * Clear all encrypted data (keeps encryption key)
   */
  async clear() {
    return new Promise((resolve, reject) => {
      chrome.storage.local.get(null, (all) => {
        if (chrome.runtime.lastError) {
          reject(chrome.runtime.lastError);
          return;
        }

        const encryptedKeys = Object.keys(all).filter(k => k.startsWith('_enc_'));
        if (encryptedKeys.length === 0) {
          resolve();
          return;
        }

        chrome.storage.local.remove(encryptedKeys, () => {
          if (chrome.runtime.lastError) {
            reject(chrome.runtime.lastError);
          } else {
            resolve();
          }
        });
      });
    });
  }
}

// Export singleton instance
const encryptedStorage = new EncryptedStorage();

// Auto-initialize on import
encryptedStorage.init().catch(err => {
  console.error('[EncryptedStorage] Initialization failed:', err);
});
