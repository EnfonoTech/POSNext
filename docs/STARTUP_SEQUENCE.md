# FatehPOS Startup Sequence

This document describes the initialization flow of the FatehPOS frontend application, from initial page load to fully interactive state.

## Overview

The application follows an optimized startup sequence designed for:
- **Fast time-to-interactive** via parallel operations
- **Offline support** with PWA service worker
- **Secure API calls** with CSRF token management
- **Reduced API calls** via bootstrap data preloading

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Application Startup                          │
├─────────────────────────────────────────────────────────────────────┤
│  1. PWA Service Worker Registration (async, non-blocking)          │
│  2. Vue App Configuration (plugins, global components)             │
│  3. Authentication (CSRF + User - parallel)                        │
│  4. Bootstrap Data Preload (non-blocking)                          │
│  5. Router Registration & App Mount                                │
│  6. Scheduled CSRF Refresh (every 30 min)                          │
└─────────────────────────────────────────────────────────────────────┘
```

## Detailed Sequence

### 1. PWA Service Worker Registration

**File:** `POS/src/main.js`

The service worker enables offline functionality and caching. Registration happens after the `window.load` event to avoid blocking initial render.

```javascript
if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
        import("virtual:pwa-register").then(({ registerSW }) => {
            registerSW({
                immediate: true,
                onNeedRefresh: () => { /* New content available */ },
                onOfflineReady: () => { /* App ready for offline use */ },
            })
        })
    }, { passive: true })
}
```

**Key points:**
- Uses `{ passive: true }` for better scroll performance
- Dynamic import reduces initial bundle size
- Non-blocking - app continues loading in parallel

### 2. Vue App Configuration

**File:** `POS/src/main.js`

The Vue application is configured with plugins and global components before any async operations.

```javascript
const app = createApp(App)
const pinia = createPinia()

// Plugins
app.use(pinia)              // State management
app.use(resourcesPlugin)    // Frappe-UI resources
app.use(pageMetaPlugin)     // Page meta tags
app.use(translationPlugin)  // i18n support

// Global components (available in all templates without import)
app.component("Button", Button)
app.component("Dialog", Dialog)
app.component("Input", Input)
// ... etc
```

**Global components registered:**
- `Button`, `TextInput`, `Input`, `FormControl`
- `ErrorMessage`, `Dialog`, `Alert`, `Badge`

### 3. Authentication (Parallel Loading)

**Files:** `POS/src/main.js`, `POS/src/utils/csrf.js`

CSRF token initialization and user authentication run **in parallel** for faster startup (~200-300ms savings).

```
┌──────────────────────────────────────────────────────────────┐
│                    Authentication Phase                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌─────────────────────┐     ┌─────────────────────┐       │
│   │   CSRF Promise      │     │   User Promise      │       │
│   ├─────────────────────┤     ├─────────────────────┤       │
│   │ 1. Check cookie     │     │ 1. Fetch user data  │       │
│   │ 2. Fetch if missing │     │ 2. Set session      │       │
│   │ 3. Sync to worker   │     │                     │       │
│   └─────────────────────┘     └─────────────────────┘       │
│            │                           │                     │
│            └───────────┬───────────────┘                     │
│                        ▼                                     │
│              Promise.all([csrf, user])                       │
│                        │                                     │
│                        ▼                                     │
│              session.user = user                             │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**CSRF Token Flow:**
1. Check for existing token in cookie
2. If missing, fetch from server via `ensureCSRFToken()`
3. Sync token to offline worker for authenticated requests
4. Register callback for token refresh events

**User Authentication Flow:**
1. Fetch user resource via `userResource.fetch()`
2. On success, extract session user
3. On failure, user remains logged out (guest mode)

### 4. Bootstrap Data Preload

**Files:** `POS/src/stores/bootstrap.js`, `pos_next/api/bootstrap.py`

After authentication, the app preloads essential data in a single API call instead of multiple sequential calls.

```
┌──────────────────────────────────────────────────────────────┐
│                   Bootstrap API Response                      │
├──────────────────────────────────────────────────────────────┤
│  {                                                           │
│    "success": true,                                          │
│    "locale": "ar",              // User's language           │
│    "shift": { ... },            // Active POS shift          │
│    "pos_profile": { ... },      // POS Profile settings      │
│    "pos_settings": { ... },     // FatehPOS settings         │
│    "payment_methods": [...]     // Available payments        │
│  }                                                           │
└──────────────────────────────────────────────────────────────┘
```

**Performance benefit:** ~300-500ms faster initial load by avoiding:
- Separate locale fetch
- Separate shift check
- Separate POS profile load
- Separate settings load
- Separate payment methods fetch

**Non-blocking:** Bootstrap runs in the background via dynamic import to not delay app mount.

```javascript
if (user) {
    import("./stores/bootstrap")
        .then(({ useBootstrapStore }) => {
            useBootstrapStore().loadInitialData()
        })
}
```

### 5. Router & App Mount

**File:** `POS/src/main.js`

After authentication completes, the router is registered and the app is mounted.

```javascript
app.use(router)
app.mount("#app")
```

The router uses the session state to determine initial navigation (login page vs. POS page).

### 6. Scheduled CSRF Refresh

**File:** `POS/src/main.js`

CSRF tokens expire, so the app refreshes them every 30 minutes while running.

```javascript
setInterval(async () => {
    await ensureCSRFToken({ forceRefresh: true, silent: true })
    await syncCSRFTokenToWorker()
}, 30 * 60 * 1000)
```

## Data Flow: Bootstrap → Stores

Other stores check bootstrap data before making their own API calls:

```
┌─────────────────────────────────────────────────────────────────────┐
│                       Store Data Loading                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────────────┐                                               │
│   │ Bootstrap Store │                                               │
│   │ (Single API)    │                                               │
│   └────────┬────────┘                                               │
│            │                                                        │
│            ▼                                                        │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │              Other Stores Check Bootstrap First              │  │
│   ├─────────────────────────────────────────────────────────────┤  │
│   │                                                             │  │
│   │  posSettingsStore.loadSettings():                           │  │
│   │    1. Check bootstrapStore.getPreloadedPOSSettings()        │  │
│   │    2. If found → use preloaded data                         │  │
│   │    3. If not → fallback to API call                         │  │
│   │                                                             │  │
│   │  useLocale.initLocale():                                    │  │
│   │    1. Check bootstrapStore.getPreloadedLocale()             │  │
│   │    2. If found → apply locale immediately                   │  │
│   │    3. If not → fallback to API call                         │  │
│   │                                                             │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Lazy Loading Strategies

Some data is intentionally **not** loaded at startup to reduce initial load time:

| Data | When Loaded | Reason |
|------|-------------|--------|
| Countries list | CreateCustomerDialog opens | Large dataset, rarely needed |
| Item images | Item visible in viewport | Network optimization |
| Translations | Language change | Only needed for non-default locale |

## Offline Worker Integration

The offline worker requires the CSRF token for authenticated requests. Token sync happens:

1. **At startup** - After CSRF token initialization
2. **On refresh** - When token is refreshed (via callback)
3. **On schedule** - Every 30 minutes with the refresh cycle

```javascript
// Register callback for token refresh events
onCSRFTokenRefresh((newToken) => {
    offlineWorker.setCSRFToken(newToken)
})
```

## Performance Timeline

Typical startup timeline on fast connection:

```
0ms    ─┬─ Page load begins
        │
50ms   ─┼─ Service worker registration starts (async)
        │
100ms  ─┼─ Vue app configured
        │
150ms  ─┼─ CSRF + User fetch starts (parallel)
        │
350ms  ─┼─ Auth complete, app mounts
        │
400ms  ─┼─ Bootstrap preload starts (background)
        │
600ms  ─┴─ Bootstrap complete, all data ready
```

## Error Handling

Each phase has graceful fallbacks:

| Phase | Failure Behavior |
|-------|------------------|
| Service Worker | App works without offline support |
| CSRF Token | Retries on first API call |
| User Auth | Redirects to login page |
| Bootstrap | Individual stores make their own API calls |

## Related Files

- `POS/src/main.js` - Main entry point
- `POS/src/utils/csrf.js` - CSRF token management
- `POS/src/stores/bootstrap.js` - Bootstrap store
- `POS/src/data/session.js` - Session management
- `POS/src/data/user.js` - User resource
- `pos_next/api/bootstrap.py` - Bootstrap API endpoint
