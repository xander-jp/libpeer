#include <stdio.h>
#include <string.h>
#include <stdint.h>

#include "pico/stdlib.h"
#include "hardware/uart.h"
#include "hardware/gpio.h"
#include "pico/cyw43_arch.h"
#include "bsp/board.h"

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
// WiFi initialization
//=============================================================================
static int wifi_init(void) {
    if (cyw43_arch_init()) {
        printf("WiFi init failed\n");
        return -1;
    }

    // Quick blink to confirm cyw43 init succeeded
    for (int i = 0; i < 3; i++) {
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);
        sleep_ms(100);
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0);
        sleep_ms(100);
    }

    cyw43_arch_enable_sta_mode();

    g_time_wifi_start = board_millis();
    printf("[TIMING] WiFi connection start: %lu ms\n", (unsigned long)g_time_wifi_start);
    printf("Connecting to WiFi '%s'...\n", WIFI_SSID);

    if (cyw43_arch_wifi_connect_timeout_ms(
            WIFI_SSID,
            WIFI_PASSWORD,
            CYW43_AUTH_WPA2_AES_PSK,
            30000)) {
        printf("WiFi connection failed\n");
        return -1;
    }

    g_time_wifi_done = board_millis();
    printf("[TIMING] WiFi connected: %lu ms (took %lu ms)\n",
           (unsigned long)g_time_wifi_done,
           (unsigned long)(g_time_wifi_done - g_time_wifi_start));

    // Blink LED to confirm board is running
    for (int i = 0; i < 10; i++) {
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);
        sleep_ms(200);
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0);
        sleep_ms(200);
    }
    cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);

    return 0;
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
