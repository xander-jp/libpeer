#include <stdio.h>
#include <string.h>
#include <stdint.h>

#include "pico/stdlib.h"
#include "hardware/uart.h"
#include "hardware/gpio.h"
#include "pico/cyw43_arch.h"
#include "bsp/board.h"
#include "lwip/dns.h"
#include "lwip/ip_addr.h"

#include "peer.h"

//=============================================================================
// Configuration - set via environment variables or defaults below
// Build with: SIGNALING_URL=... WIFI_SSID=... cmake ..
//=============================================================================
#ifndef WIFI_SSID
#define WIFI_SSID       "your-wifi-ssid"
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD   "your-wifi-password"
#endif
#ifndef SIGNALING_URL
#define SIGNALING_URL   "http://localhost:8080/webrtc"
#endif
#ifndef SIGNALING_TOKEN
#define SIGNALING_TOKEN ""
#endif

//=============================================================================
// Global state
//=============================================================================
static PeerConnection* g_pc = NULL;
static PeerConnectionState g_state = PEER_CONNECTION_NEW;
static uint32_t g_dcmsg_time = 0;
static int g_count = 0;

//=============================================================================
// Timing measurement
//=============================================================================
static uint32_t g_time_boot = 0;           // Boot time (reference)
static uint32_t g_time_wifi_start = 0;     // WiFi connection start
static uint32_t g_time_wifi_done = 0;      // WiFi connected
static uint32_t g_time_signaling_start = 0;// Signaling server connect start
static uint32_t g_time_ice_checking = 0;   // ICE checking started
static uint32_t g_time_ice_connected = 0;  // ICE connected (DTLS starts)
static uint32_t g_time_ice_completed = 0;  // ICE completed
static uint32_t g_time_datachannel_open = 0; // DataChannel opened (SCTP ready)
static uint32_t g_time_first_rx = 0;       // First message received
static uint32_t g_time_first_tx = 0;       // First message sent
static bool g_first_rx_logged = false;
static bool g_first_tx_logged = false;

#define LOG_TIMING(label) printf("[TIMING] %s: %lu ms\n", (label), (unsigned long)board_millis())

//=============================================================================
// LED blink state machine (non-blocking)
//=============================================================================
typedef struct {
    uint32_t interval_ms;   // Blink interval
    int remaining;          // Remaining blink count
    uint32_t last_toggle;   // Last toggle time
    bool led_on;            // Current LED state
} LedBlinkState;

static LedBlinkState g_led_blink = {0, 0, 0, false};

// Start a blink pattern
static void led_blink_start(uint32_t interval_ms, int count) {
    g_led_blink.interval_ms = interval_ms;
    g_led_blink.remaining = count * 2;  // Each blink = on + off
    g_led_blink.last_toggle = board_millis();
    g_led_blink.led_on = true;
    cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);
}

// Process LED blink (call from main loop)
static void led_blink_loop(void) {
    if (g_led_blink.remaining <= 0) return;

    uint32_t now = board_millis();
    if ((now - g_led_blink.last_toggle) >= g_led_blink.interval_ms) {
        g_led_blink.last_toggle = now;
        g_led_blink.remaining--;

        if (g_led_blink.remaining > 0) {
            g_led_blink.led_on = !g_led_blink.led_on;
            cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, g_led_blink.led_on ? 1 : 0);
        } else {
            // Done blinking - turn off LED
            cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0);
            g_led_blink.led_on = false;
        }
    }
}

// TX: 100ms x 3 blinks (ピッ・ピッ・ピッ)
static void led_blink_tx(void) {
    led_blink_start(100, 3);
}

// RX: 20ms x 15 blinks (ピピピピピ...)
static void led_blink_rx(void) {
    led_blink_start(20, 15);
}

//=============================================================================
// Callbacks
//=============================================================================
static void onconnectionstatechange(PeerConnectionState state, void* data) {
    uint32_t now = board_millis();
    printf("[TIMING] State -> %s: %lu ms\n", peer_connection_state_to_string(state), (unsigned long)now);

    switch (state) {
        case PEER_CONNECTION_CHECKING:
            g_time_ice_checking = now;
            printf("[TIMING] ICE checking started: %lu ms (WiFi+%lu ms)\n",
                   (unsigned long)now, (unsigned long)(now - g_time_wifi_done));
            break;
        case PEER_CONNECTION_CONNECTED:
            g_time_ice_connected = now;
            printf("[TIMING] ICE connected (DTLS starting): %lu ms (ICE took %lu ms)\n",
                   (unsigned long)now, (unsigned long)(now - g_time_ice_checking));
            break;
        case PEER_CONNECTION_COMPLETED:
            g_time_ice_completed = now;
            printf("[TIMING] ICE completed: %lu ms\n", (unsigned long)now);
            break;
        default:
            break;
    }
    g_state = state;
}

static void onopen(void* user_data) {
    g_time_datachannel_open = board_millis();
    printf("[TIMING] DataChannel opened (SCTP ready): %lu ms\n", (unsigned long)g_time_datachannel_open);
    printf("[TIMING] DTLS+SCTP took: %lu ms (from ICE connected)\n",
           (unsigned long)(g_time_datachannel_open - g_time_ice_connected));
    printf("[TIMING] Total connection time: %lu ms (from boot)\n",
           (unsigned long)g_time_datachannel_open);
}

static void onclose(void* user_data) {
    printf("DataChannel closed\n");
}

static void onmessage(char* msg, size_t len, void* user_data, uint16_t sid) {
    // Log first RX timing
    if (!g_first_rx_logged) {
        g_time_first_rx = board_millis();
        g_first_rx_logged = true;
        printf("[TIMING] First message RX: %lu ms (from boot)\n", (unsigned long)g_time_first_rx);
        printf("[TIMING] Time from DataChannel open to first RX: %lu ms\n",
               (unsigned long)(g_time_first_rx - g_time_datachannel_open));
    }

    printf("Message [%d]: %.*s", sid, (int)len, msg);

    // RX blink: 20ms x 15 (ピピピピピ...)
    led_blink_rx();

    if (len >= 4 && strncmp(msg, "ping", 4) == 0) {
        printf(" -> pong");
        peer_connection_datachannel_send(g_pc, "pong", 4);
        // TX blink: 100ms x 3 (ピッ・ピッ・ピッ)
        led_blink_tx();
    }
    printf("\n");
}

//=============================================================================
// WiFi timing variables
//=============================================================================
static uint32_t g_time_wifi_scan_start = 0;
static uint32_t g_time_wifi_auth_start = 0;
static uint32_t g_time_wifi_auth_done = 0;
static uint32_t g_time_dhcp_start = 0;
static uint32_t g_time_dhcp_done = 0;

//=============================================================================
// WiFi initialization (detailed timing)
//=============================================================================
static int wifi_init(void) {
    int last_status = CYW43_LINK_DOWN;
    int status;
    uint32_t now;
    uint32_t timeout_start;

    if (cyw43_arch_init()) {
        printf("WiFi init failed\n");
        return -1;
    }

    // Quick blink to confirm cyw43 init succeeded (disabled for timing measurement)
    // for (int i = 0; i < 3; i++) {
    //     cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);
    //     sleep_ms(100);
    //     cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0);
    //     sleep_ms(100);
    // }

    cyw43_arch_enable_sta_mode();

    // Start async WiFi connection
    g_time_wifi_start = board_millis();
    g_time_wifi_scan_start = g_time_wifi_start;
    printf("[TIMING] WiFi scan start: %lu ms\n", (unsigned long)g_time_wifi_scan_start);
    printf("Connecting to WiFi '%s'...\n", WIFI_SSID);

    if (cyw43_arch_wifi_connect_async(WIFI_SSID, WIFI_PASSWORD, CYW43_AUTH_WPA2_AES_PSK) != 0) {
        printf("WiFi connect_async failed\n");
        return -1;
    }

    // Poll for connection status with detailed timing
    timeout_start = board_millis();
    while (1) {
        cyw43_arch_poll();
        sleep_ms(10);

        now = board_millis();
        if ((now - timeout_start) > 30000) {
            printf("WiFi connection timeout\n");
            return -1;
        }

        status = cyw43_tcpip_link_status(&cyw43_state, CYW43_ITF_STA);

        // Detect state transitions
        if (status != last_status) {
            switch (status) {
                case CYW43_LINK_JOIN:
                    // Auth/Assoc completed (scan also done at this point)
                    g_time_wifi_auth_done = now;
                    printf("[TIMING] WiFi scan done: %lu ms (took %lu ms)\n",
                           (unsigned long)now, (unsigned long)(now - g_time_wifi_scan_start));
                    printf("[TIMING] WiFi auth/assoc done: %lu ms\n", (unsigned long)now);
                    break;

                case CYW43_LINK_NOIP:
                    // Link up, waiting for DHCP
                    g_time_dhcp_start = now;
                    printf("[TIMING] DHCP start: %lu ms\n", (unsigned long)now);
                    break;

                case CYW43_LINK_UP:
                    // DHCP completed, got IP
                    g_time_dhcp_done = now;
                    g_time_wifi_done = now;
                    printf("[TIMING] DHCP bound: %lu ms (took %lu ms)\n",
                           (unsigned long)now, (unsigned long)(now - g_time_dhcp_start));
                    printf("[TIMING] WiFi fully connected: %lu ms (total %lu ms)\n",
                           (unsigned long)now, (unsigned long)(now - g_time_wifi_start));
                    goto wifi_connected;

                case CYW43_LINK_FAIL:
                    printf("WiFi connection failed\n");
                    return -1;

                case CYW43_LINK_NONET:
                    printf("WiFi: No matching SSID found\n");
                    return -1;

                case CYW43_LINK_BADAUTH:
                    printf("WiFi: Authentication failure\n");
                    return -1;

                default:
                    break;
            }
            last_status = status;
        }
    }

wifi_connected:
    // Blink LED to confirm WiFi connected (disabled for timing measurement)
    // for (int i = 0; i < 5; i++) {
    //     cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);
    //     sleep_ms(100);
    //     cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0);
    //     sleep_ms(100);
    // }
    // cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);

    return 0;
}

//=============================================================================
// DNS resolution timing
//=============================================================================
static uint32_t g_time_dns_start = 0;
static uint32_t g_time_dns_done = 0;
static volatile bool g_dns_done = false;
static ip_addr_t g_dns_result;

static void dns_callback(const char *name, const ip_addr_t *ipaddr, void *arg) {
    g_time_dns_done = board_millis();
    if (ipaddr) {
        g_dns_result = *ipaddr;
        printf("[TIMING] DNS resolved: %lu ms (took %lu ms) -> %s\n",
               (unsigned long)g_time_dns_done,
               (unsigned long)(g_time_dns_done - g_time_dns_start),
               ipaddr_ntoa(ipaddr));
    } else {
        printf("[TIMING] DNS resolution failed: %lu ms\n", (unsigned long)g_time_dns_done);
    }
    g_dns_done = true;
}

// Extract hostname from URL (e.g., "http://example.com:8080/path" -> "example.com")
static void extract_hostname(const char *url, char *hostname, size_t hostname_size) {
    const char *start = url;
    const char *end;

    // Skip protocol
    if (strncmp(url, "http://", 7) == 0) start = url + 7;
    else if (strncmp(url, "https://", 8) == 0) start = url + 8;

    // Find end of hostname (port or path)
    end = start;
    while (*end && *end != ':' && *end != '/') end++;

    size_t len = end - start;
    if (len >= hostname_size) len = hostname_size - 1;
    memcpy(hostname, start, len);
    hostname[len] = '\0';
}

//=============================================================================
// WebRTC initialization
//=============================================================================
static int webrtc_init(void) {
    PeerConfiguration config = {
        .ice_servers = {
            {.urls = "stun:stun.l.google.com:19302"},
        },
        .datachannel = DATA_CHANNEL_STRING,
        .video_codec = CODEC_NONE,
        .audio_codec = CODEC_NONE,
    };

    printf("Initializing WebRTC...\n");
    peer_init();

    g_pc = peer_connection_create(&config);
    if (!g_pc) {
        printf("Failed to create PeerConnection\n");
        return -1;
    }

    peer_connection_oniceconnectionstatechange(g_pc, onconnectionstatechange);
    peer_connection_ondatachannel(g_pc, onmessage, onopen, onclose);

    // DNS resolution test for signaling server
    char hostname[128];
    extract_hostname(SIGNALING_URL, hostname, sizeof(hostname));

    g_time_dns_start = board_millis();
    printf("[TIMING] DNS lookup start: %lu ms (host: %s)\n", (unsigned long)g_time_dns_start, hostname);

    g_dns_done = false;
    err_t err = dns_gethostbyname(hostname, &g_dns_result, dns_callback, NULL);
    if (err == ERR_OK) {
        // Already cached
        g_time_dns_done = board_millis();
        printf("[TIMING] DNS resolved (cached): %lu ms -> %s\n",
               (unsigned long)g_time_dns_done, ipaddr_ntoa(&g_dns_result));
    } else if (err == ERR_INPROGRESS) {
        // Wait for DNS callback
        uint32_t dns_timeout = board_millis();
        while (!g_dns_done && (board_millis() - dns_timeout) < 10000) {
            cyw43_arch_poll();
            sleep_ms(10);
        }
        if (!g_dns_done) {
            printf("[TIMING] DNS timeout\n");
        }
    } else {
        printf("[TIMING] DNS lookup failed: err=%d\n", err);
    }

    g_time_signaling_start = board_millis();
    printf("[TIMING] Signaling server connect start: %lu ms\n", (unsigned long)g_time_signaling_start);
    printf("Connecting to signaling server: %s\n", SIGNALING_URL);
    peer_signaling_connect(SIGNALING_URL,
                           SIGNALING_TOKEN[0] ? SIGNALING_TOKEN : NULL,
                           g_pc);

    return 0;
}

//=============================================================================
// Main loop
//=============================================================================
int main() {
    uint32_t now;

    // Explicit UART setup for RP2350 compatibility
    uart_init(uart0, 115200);
    gpio_set_function(0, GPIO_FUNC_UART);  // TX
    gpio_set_function(1, GPIO_FUNC_UART);  // RX

    stdio_init_all();

    // Wait for serial
    sleep_ms(2000);
    g_time_boot = board_millis();
    printf("\n\n=== RP2350 WebRTC Demo ===\n");
    printf("[TIMING] Boot complete: %lu ms\n", (unsigned long)g_time_boot);

    // USB HID init
    board_init();
    tusb_init();

    // WiFi init
    if (wifi_init() != 0) {
        printf("WiFi init failed, halting\n");
        while (1) {
            sleep_ms(1000);
        }
    }

    // WebRTC init
    if (webrtc_init() != 0) {
        printf("WebRTC init failed, halting\n");
        while (1) {
            sleep_ms(1000);
        }
    }

    printf("Entering main loop...\n");

    // Main loop - single threaded
    while (1) {
        // Process lwIP network events
        cyw43_arch_poll();

        // Process signaling
        peer_signaling_loop();

        // Process peer connection
        peer_connection_loop(g_pc);

        // Send periodic datachannel message when connected
        if (g_state == PEER_CONNECTION_COMPLETED) {
            now = board_millis();
            if ((now - g_dcmsg_time) > 1000) {
                g_dcmsg_time = now;
                char msg[64];
                snprintf(msg, sizeof(msg), "datachannel message: %05d", g_count++);
                peer_connection_datachannel_send(g_pc, msg, strlen(msg));

                // Log first TX timing
                if (!g_first_tx_logged) {
                    g_time_first_tx = board_millis();
                    g_first_tx_logged = true;
                    printf("[TIMING] First message TX: %lu ms (from boot)\n", (unsigned long)g_time_first_tx);
                    printf("[TIMING] Time from DataChannel open to first TX: %lu ms\n",
                           (unsigned long)(g_time_first_tx - g_time_datachannel_open));
                }

                // TX blink: 100ms x 3 (ピッ・ピッ・ピッ)
                led_blink_tx();
            }
        }

        // Process LED blink pattern
        led_blink_loop();

        // Small delay to prevent busy loop
        sleep_us(100);
    }

    // Cleanup (never reached in bare metal)
    peer_signaling_disconnect();
    peer_connection_destroy(g_pc);
    peer_deinit();
    cyw43_arch_deinit();

    return 0;
}
