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
    printf("State changed: %s\n", peer_connection_state_to_string(state));
    g_state = state;
}

static void onopen(void* user_data) {
    printf("DataChannel opened\n");
}

static void onclose(void* user_data) {
    printf("DataChannel closed\n");
}

static void onmessage(char* msg, size_t len, void* user_data, uint16_t sid) {
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
    printf("Connecting to WiFi '%s'...\n", WIFI_SSID);

    if (cyw43_arch_wifi_connect_timeout_ms(
            WIFI_SSID,
            WIFI_PASSWORD,
            CYW43_AUTH_WPA2_AES_PSK,
            30000)) {
        printf("WiFi connection failed\n");
        return -1;
    }

    printf("WiFi connected\n");

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
    printf("\n\n=== RP2350 WebRTC Demo ===\n");

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
