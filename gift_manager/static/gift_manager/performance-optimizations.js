/**
 * Performance Optimizations for AJAX Requests and Caching
 * Implements request debouncing, caching, and database query optimization
 * Requirements: 7.5, 8.5
 */

(function(window) {
    'use strict';

    /**
     * Configuration for performance optimizations
     */
    const PERFORMANCE_CONFIG = {
        // Debouncing delays (milliseconds)
        debounce: {
            search: 300,
            filter: 200,
            formInput: 500,
            resize: 250
        },

        // Cache settings
        cache: {
            maxAge: 5 * 60 * 1000, // 5 minutes
            maxEntries: 100,
            keyPrefix: 'gm_cache_'
        },

        // Request optimization
        requests: {
            batchDelay: 50, // Batch requests within 50ms
            maxConcurrent: 3, // Maximum concurrent requests
            retryAttempts: 2,
            retryDelay: 1000
        }
    };

    /**
     * Request cache implementation
     */
    class RequestCache {
        constructor() {
            this.cache = new Map();
            this.timestamps = new Map();
        }

        /**
         * Generate cache key from URL and parameters
         */
        generateKey(url, params = {}) {
            const paramString = Object.keys(params)
                .sort()
                .map(key => `${key}=${params[key]}`)
                .join('&');
            return `${PERFORMANCE_CONFIG.cache.keyPrefix}${url}${paramString ? '?' + paramString : ''}`;
        }

        /**
         * Get cached response if valid
         */
        get(url, params = {}) {
            const key = this.generateKey(url, params);
            const timestamp = this.timestamps.get(key);

            if (!timestamp) return null;

            // Check if cache entry is still valid
            if (Date.now() - timestamp > PERFORMANCE_CONFIG.cache.maxAge) {
                this.delete(key);
                return null;
            }

            return this.cache.get(key);
        }

        /**
         * Store response in cache
         */
        set(url, params = {}, response) {
            const key = this.generateKey(url, params);

            // Enforce cache size limit
            if (this.cache.size >= PERFORMANCE_CONFIG.cache.maxEntries) {
                this.evictOldest();
            }

            this.cache.set(key, response);
            this.timestamps.set(key, Date.now());
        }

        /**
         * Delete cache entry
         */
        delete(key) {
            this.cache.delete(key);
            this.timestamps.delete(key);
        }

        /**
         * Clear all cache entries
         */
        clear() {
            this.cache.clear();
            this.timestamps.clear();
        }

        /**
         * Evict oldest cache entry
         */
        evictOldest() {
            let oldestKey = null;
            let oldestTime = Date.now();

            for (const [key, timestamp] of this.timestamps.entries()) {
                if (timestamp < oldestTime) {
                    oldestTime = timestamp;
                    oldestKey = key;
                }
            }

            if (oldestKey) {
                this.delete(oldestKey);
            }
        }

        /**
         * Invalidate cache entries matching pattern
         */
        invalidatePattern(pattern) {
            const regex = new RegExp(pattern);
            const keysToDelete = [];

            for (const key of this.cache.keys()) {
                if (regex.test(key)) {
                    keysToDelete.push(key);
                }
            }

            keysToDelete.forEach(key => this.delete(key));
        }
    }

    /**
     * Request debouncer implementation
     */
    class RequestDebouncer {
        constructor() {
            this.timers = new Map();
            this.pendingRequests = new Map();
        }

        /**
         * Debounce a request
         */
        debounce(key, callback, delay) {
            // Clear existing timer
            if (this.timers.has(key)) {
                clearTimeout(this.timers.get(key));
            }

            // Set new timer
            const timer = setTimeout(() => {
                this.timers.delete(key);
                callback();
            }, delay);

            this.timers.set(key, timer);
        }

        /**
         * Cancel debounced request
         */
        cancel(key) {
            if (this.timers.has(key)) {
                clearTimeout(this.timers.get(key));
                this.timers.delete(key);
            }
        }

        /**
         * Clear all debounced requests
         */
        clear() {
            for (const timer of this.timers.values()) {
                clearTimeout(timer);
            }
            this.timers.clear();
        }
    }

    /**
     * Request queue for batching and concurrency control
     */
    class RequestQueue {
        constructor() {
            this.queue = [];
            this.activeRequests = 0;
            this.batchTimer = null;
        }

        /**
         * Add request to queue
         */
        enqueue(requestConfig) {
            this.queue.push(requestConfig);
            this.scheduleBatch();
        }

        /**
         * Schedule batch processing
         */
        scheduleBatch() {
            if (this.batchTimer) return;

            this.batchTimer = setTimeout(() => {
                this.processBatch();
                this.batchTimer = null;
            }, PERFORMANCE_CONFIG.requests.batchDelay);
        }

        /**
         * Process queued requests
         */
        processBatch() {
            while (this.queue.length > 0 && this.activeRequests < PERFORMANCE_CONFIG.requests.maxConcurrent) {
                const requestConfig = this.queue.shift();
                this.executeRequest(requestConfig);
            }
        }

        /**
         * Execute individual request
         */
        async executeRequest(requestConfig) {
            this.activeRequests++;

            try {
                const response = await this.performRequest(requestConfig);
                if (requestConfig.onSuccess) {
                    requestConfig.onSuccess(response);
                }
            } catch (error) {
                if (requestConfig.onError) {
                    requestConfig.onError(error);
                }
            } finally {
                this.activeRequests--;
                // Process next batch if queue has items
                if (this.queue.length > 0) {
                    setTimeout(() => this.processBatch(), 10);
                }
            }
        }

        /**
         * Perform the actual request with retry logic
         */
        async performRequest(requestConfig, attempt = 1) {
            try {
                const response = await fetch(requestConfig.url, requestConfig.options);

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                return response;
            } catch (error) {
                if (attempt < PERFORMANCE_CONFIG.requests.retryAttempts) {
                    await new Promise(resolve =>
                        setTimeout(resolve, PERFORMANCE_CONFIG.requests.retryDelay * attempt)
                    );
                    return this.performRequest(requestConfig, attempt + 1);
                }
                throw error;
            }
        }
    }

    /**
     * Optimized AJAX request handler
     */
    class OptimizedAjax {
        constructor() {
            this.cache = new RequestCache();
            this.debouncer = new RequestDebouncer();
            this.queue = new RequestQueue();
        }

        /**
         * Make optimized AJAX request
         */
        async request(url, options = {}) {
            const method = options.method || 'GET';
            const params = options.params || {};
            const useCache = options.cache !== false && method === 'GET';
            const debounceKey = options.debounceKey;
            const debounceDelay = options.debounceDelay || 0;

            // Check cache first for GET requests
            if (useCache) {
                const cached = this.cache.get(url, params);
                if (cached) {
                    console.log('[OptimizedAjax] Cache hit:', url);
                    return cached.clone();
                }
            }

            // Create request configuration
            const requestConfig = {
                url: this.buildUrl(url, params),
                options: {
                    method,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'HX-Request': 'true',
                        ...options.headers
                    },
                    credentials: 'same-origin',
                    ...options
                },
                onSuccess: (response) => {
                    // Cache successful GET responses
                    if (useCache && response.ok) {
                        this.cache.set(url, params, response.clone());
                    }
                    if (options.onSuccess) {
                        options.onSuccess(response);
                    }
                },
                onError: options.onError
            };

            // Handle debouncing
            if (debounceKey && debounceDelay > 0) {
                return new Promise((resolve, reject) => {
                    this.debouncer.debounce(debounceKey, () => {
                        requestConfig.onSuccess = (response) => {
                            if (useCache && response.ok) {
                                this.cache.set(url, params, response.clone());
                            }
                            resolve(response);
                        };
                        requestConfig.onError = reject;
                        this.queue.enqueue(requestConfig);
                    }, debounceDelay);
                });
            }

            // Queue request for batch processing
            return new Promise((resolve, reject) => {
                requestConfig.onSuccess = (response) => {
                    if (useCache && response.ok) {
                        this.cache.set(url, params, response.clone());
                    }
                    resolve(response);
                };
                requestConfig.onError = reject;
                this.queue.enqueue(requestConfig);
            });
        }

        /**
         * Build URL with parameters
         */
        buildUrl(url, params) {
            if (!params || Object.keys(params).length === 0) {
                return url;
            }

            const urlObj = new URL(url, window.location.origin);
            Object.keys(params).forEach(key => {
                urlObj.searchParams.set(key, params[key]);
            });
            return urlObj.toString();
        }

        /**
         * Invalidate cache for specific patterns
         */
        invalidateCache(pattern) {
            this.cache.invalidatePattern(pattern);
        }

        /**
         * Clear all caches
         */
        clearCache() {
            this.cache.clear();
        }

        /**
         * Cancel debounced requests
         */
        cancelDebounced(key) {
            this.debouncer.cancel(key);
        }
    }

    /**
     * Enhanced search functionality with debouncing and caching
     */
    function enhanceSearchPerformance() {
        const searchInputs = document.querySelectorAll('[data-search-target]');

        searchInputs.forEach(input => {
            const targetSelector = input.dataset.searchTarget;
            const debounceKey = `search_${targetSelector}`;

            input.addEventListener('input', (e) => {
                const query = e.target.value.trim();

                window.OptimizedAjax.request(window.location.href, {
                    params: { search: query, ajax: '1' },
                    debounceKey: debounceKey,
                    debounceDelay: PERFORMANCE_CONFIG.debounce.search,
                    onSuccess: async (response) => {
                        const html = await response.text();
                        const parser = new DOMParser();
                        const doc = parser.parseFromString(html, 'text/html');
                        const newContent = doc.querySelector(targetSelector);

                        if (newContent) {
                            const target = document.querySelector(targetSelector);
                            if (target) {
                                target.innerHTML = newContent.innerHTML;
                            }
                        }
                    }
                });
            });
        });
    }

    /**
     * Enhanced form submission with optimizations
     */
    function enhanceFormPerformance() {
        document.addEventListener('submit', (e) => {
            const form = e.target;
            if (!form.dataset.optimized) return;

            e.preventDefault();

            const formData = new FormData(form);
            const debounceKey = `form_${form.id || 'default'}`;

            window.OptimizedAjax.request(form.action || window.location.href, {
                method: form.method || 'POST',
                body: formData,
                cache: false, // Don't cache form submissions
                debounceKey: debounceKey,
                debounceDelay: PERFORMANCE_CONFIG.debounce.formInput,
                onSuccess: async (response) => {
                    // Handle successful form submission
                    if (response.headers.get('HX-Trigger')) {
                        const triggers = response.headers.get('HX-Trigger').split(',');
                        triggers.forEach(trigger => {
                            document.dispatchEvent(new CustomEvent(trigger.trim()));
                        });
                    }
                },
                onError: (error) => {
                    console.error('Form submission error:', error);
                }
            });
        });
    }

    /**
     * Preload critical resources
     */
    function preloadCriticalResources() {
        const criticalUrls = [
            '/api/auth/status/',
            '/static/gift_manager/css/modern-ux.css',
            '/static/gift_manager/js/htmx.min.js'
        ];

        criticalUrls.forEach(url => {
            window.OptimizedAjax.request(url, {
                cache: true,
                onSuccess: () => console.log(`[Performance] Preloaded: ${url}`)
            });
        });
    }

    /**
     * Monitor and optimize performance
     */
    function setupPerformanceMonitoring() {
        // Monitor cache hit rate
        let cacheHits = 0;
        let cacheMisses = 0;

        const originalGet = window.OptimizedAjax.cache.get;
        window.OptimizedAjax.cache.get = function(...args) {
            const result = originalGet.apply(this, args);
            if (result) {
                cacheHits++;
            } else {
                cacheMisses++;
            }
            return result;
        };

        // Log performance metrics periodically
        setInterval(() => {
            const total = cacheHits + cacheMisses;
            if (total > 0) {
                const hitRate = (cacheHits / total * 100).toFixed(1);
                console.log(`[Performance] Cache hit rate: ${hitRate}% (${cacheHits}/${total})`);
            }
        }, 60000); // Every minute

        // Monitor request queue size
        setInterval(() => {
            const queueSize = window.OptimizedAjax.queue.queue.length;
            const activeRequests = window.OptimizedAjax.queue.activeRequests;

            if (queueSize > 5 || activeRequests >= PERFORMANCE_CONFIG.requests.maxConcurrent) {
                console.warn(`[Performance] High request load - Queue: ${queueSize}, Active: ${activeRequests}`);
            }
        }, 5000); // Every 5 seconds
    }

    /**
     * Initialize performance optimizations
     */
    function init() {
        // Create global optimized AJAX instance
        window.OptimizedAjax = new OptimizedAjax();

        // Enhance existing functionality
        enhanceSearchPerformance();
        enhanceFormPerformance();
        preloadCriticalResources();
        setupPerformanceMonitoring();

        // Invalidate cache on CRUD operations
        document.addEventListener('list:update', () => {
            window.OptimizedAjax.invalidateCache('.*/(persons|gifts|events|relations|groups|tags)/.*');
        });

        // Clear cache on user logout
        document.addEventListener('user:logout', () => {
            window.OptimizedAjax.clearCache();
        });

        console.log('[Performance] Optimizations initialized');
    }

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Expose public API
    window.PerformanceOptimizations = {
        OptimizedAjax: OptimizedAjax,
        RequestCache: RequestCache,
        RequestDebouncer: RequestDebouncer,
        RequestQueue: RequestQueue,
        config: PERFORMANCE_CONFIG
    };

})(window);
