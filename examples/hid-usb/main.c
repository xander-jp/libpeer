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
#include "tusb.h"
#include "pico/util/queue.h"
#include "pico/multicore.h"
#include "hardware/resets.h"
#include "hardware/structs/usb.h"


#include "peer.h"
#include "cJSON.h"

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
// HID-USB
//=============================================================================
#define USB_VID         0x413C
#define USB_PID         0x301A
#define USB_BCD         0x0100
#define POLL_TIME_S     1
enum
{
    ITF_NUM_HID,
    ITF_NUM_TOTAL
};
enum
{
    EPNUM_HID = 0x81,
    EPNUM_HID_B = 0x01
};
#define CONFIG_TOTAL_LEN  (TUD_CONFIG_DESC_LEN + TUD_HID_DESC_LEN)
#define CONFIG_TOTAL_LEN_B  (9 + 9 + 9 + 7) 
#define BUF_SIZE 2048

enum {
    PARSE_IDLE = 0,
    PARSE_VALUE,
    PARSE_DATA,
    PARSE_END
};

//=============================================================================
// Queue (core1 -> core0, multicore-safe)
//=============================================================================
#define QUEUE_SIZE     32
#define QUEUE_ITEM_LEN 128

typedef struct {
    uint8_t data[QUEUE_ITEM_LEN];
    uint16_t len;
} queue_entry_t;

static queue_t g_queue;
static void hid_task(void);

//=============================================================================
// HID USB
//=============================================================================
tusb_desc_device_t const desc_device =
{
    .bLength            = sizeof(tusb_desc_device_t),
    .bDescriptorType    = TUSB_DESC_DEVICE,
    .bcdUSB             = 0x0200,
    .bDeviceClass       = 0x00,
    .bDeviceSubClass    = 0x00,
    .bDeviceProtocol    = 0x00,
    .bMaxPacketSize0    = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor           = USB_VID,
    .idProduct          = USB_PID,
    .bcdDevice          = USB_BCD,
    .iManufacturer      = 0x01,
    .iProduct           = 0x02,
    .iSerialNumber      = 0x03,
    .bNumConfigurations = 0x01
};
uint8_t const * tud_descriptor_device_cb(void) {
    return((uint8_t const *) &desc_device);
}

uint8_t const desc_hid_report[] = {
    TUD_HID_REPORT_DESC_MOUSE(HID_REPORT_ID(1))
};
uint8_t const desc_hid_report_b[] = {
    0x05, 0x01,       // Usage Page (Generic Desktop)
    0x09, 0x02,       // Usage (Mouse)
    0xA1, 0x01,       // Collection (Application)
    0x09, 0x01,       //   Usage (Pointer)
    0xA1, 0x00,       //   Collection (Physical)
    0x05, 0x09,       //     Usage Page (Button)
    0x19, 0x01,       //     Usage Minimum (Button 1)
    0x29, 0x03,       //     Usage Maximum (Button 3)
    0x15, 0x00,       //     Logical Minimum (0)
    0x25, 0x01,       //     Logical Maximum (1)
    0x95, 0x03,       //     Report Count (3 buttons)
    0x75, 0x01,       //     Report Size (1)
    0x81, 0x02,       //     Input (Data,Var,Abs)
    0x95, 0x01,       //     Report Count (1)
    0x75, 0x05,       //     Report Size (5) padding
    0x81, 0x03,       //     Input (Const,Var,Abs)
    0x05, 0x01,       //     Usage Page (Generic Desktop)
    0x09, 0x30,       //     Usage (X)
    0x09, 0x31,       //     Usage (Y)
    0x15, 0x81,       //     Logical Minimum (-127)
    0x25, 0x7F,       //     Logical Maximum (127)
    0x75, 0x08,       //     Report Size (8)
    0x95, 0x02,       //     Report Count (2 bytes: X,Y)
    0x81, 0x06,       //     Input (Data,Var,Rel)
    0xC0,             //   End Collection
    0xC0              // End Collection
};

uint8_t const * tud_hid_descriptor_report_cb(uint8_t instance) {
    return(desc_hid_report_b);
}

uint8_t const desc_configuration[] = {
    TUD_CONFIG_DESCRIPTOR(
        1,
        ITF_NUM_TOTAL,
        0,
        CONFIG_TOTAL_LEN,
        0x00,
        100
    ), TUD_HID_DESCRIPTOR(
        ITF_NUM_HID,
        0,
        HID_ITF_PROTOCOL_MOUSE,
        sizeof(desc_hid_report_b),
        EPNUM_HID,
        8,
        10
    )
};


uint8_t const desc_configuration_b[] = {

    0x09,                       // bLength
    TUSB_DESC_CONFIGURATION,    // bDescriptorType
    (CONFIG_TOTAL_LEN_B & 0xFF),  // wTotalLength LSB
    (CONFIG_TOTAL_LEN_B >> 8),    // wTotalLength MSB
    0x01,                       // bNumInterfaces
    0x01,                       // bConfigurationValue
    0x00,                       // iConfiguration
    TUSB_DESC_CONFIG_ATT_REMOTE_WAKEUP, // bmAttributes (Bus powered + Remote Wakeup Available)
    250,                        // bMaxPower (2mA units) -> 250 = 500mA

    // ----- Interface Descriptor (HID Boot Mouse) -----
    0x09,                       // bLength
    TUSB_DESC_INTERFACE,        // bDescriptorType
    ITF_NUM_HID,                // bInterfaceNumber
    0x00,                       // bAlternateSetting
    0x01,                       // bNumEndpoints (1 IN endpoint)
    TUSB_CLASS_HID,             // bInterfaceClass (HID = 0x03)
    HID_SUBCLASS_BOOT,          // bInterfaceSubClass (Boot Interface = 0x01)
    HID_ITF_PROTOCOL_MOUSE,     // bInterfaceProtocol (Mouse = 0x02)
    0x00,                       // iInterface

    // ----- HID Descriptor -----
    0x09,                       // bLength
    HID_DESC_TYPE_HID,          // bDescriptorType (HID)
    0x11, 0x01,                 // bcdHID = 1.11
    0x00,                       // bCountryCode
    0x01,                       // bNumDescriptors
    HID_DESC_TYPE_REPORT,       // bDescriptorType (Report)
    sizeof(desc_hid_report_b) & 0xFF, // wDescriptorLength LSB
    (sizeof(desc_hid_report_b) >> 8), // wDescriptorLength MSB

    // ----- Endpoint Descriptor (INT IN) -----
    0x07,                       // bLength
    TUSB_DESC_ENDPOINT,         // bDescriptorType
    0x80 | EPNUM_HID_B,         // bEndpointAddress (IN endpoint 1)
    TUSB_XFER_INTERRUPT,        // bmAttributes (Interrupt)
    0x08, 0x00,                 // wMaxPacketSize (8 bytes)
    0x0A                        // bInterval (10ms)

};
uint8_t const * tud_descriptor_configuration_cb(uint8_t index) {
    return(desc_configuration_b);
}

char const *string_desc_arr[] = {
    (const char[]) { 0x09, 0x04 },  // 0: lang ID = 0x0409 (US-EN)
    "mx-mouse",                     // 1: Manufacturer
    "mx-mouse",                     // 2: Product
    "987654"                        // 3: Serial
};

static uint16_t _desc_str[32] = { 0x00,};

uint16_t const * tud_descriptor_string_cb(uint8_t index, uint16_t langid) {
    uint8_t chr_count;
    if (index == 0) {
        _desc_str[1] = (uint16_t) string_desc_arr[0][0] | (string_desc_arr[0][1] << 8);
        _desc_str[0] = (TUSB_DESC_STRING << 8) | (2 + 2);
        return(_desc_str);
    }

    const char *str = string_desc_arr[index];
    chr_count = (uint8_t) strlen(str);
    if (chr_count > 31) { chr_count = 31; }

    for (uint8_t i = 0; i < chr_count; i++) {
        _desc_str[1 + i] = str[i];
    }
    _desc_str[0] = (TUSB_DESC_STRING << 8) | (2 * chr_count + 2);
    return(_desc_str);
}


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
// Callbacks(PeerConnection)
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
    // RX blink: 20ms x 15
    led_blink_rx();

    // Parse JSON: {"command":"x,y,z","type":"mouse"}
    cJSON* json = cJSON_ParseWithLength(msg, len);
    if (json) {
        const cJSON* type = cJSON_GetObjectItemCaseSensitive(json, "type");
        const cJSON* command = cJSON_GetObjectItemCaseSensitive(json, "command");

        if (cJSON_IsString(type) && strcmp(type->valuestring, "mouse") == 0 &&
            cJSON_IsString(command) && command->valuestring[0] != '\0') {
            queue_entry_t entry = {0};
            entry.len = strlen(command->valuestring);
            if (entry.len > QUEUE_ITEM_LEN) entry.len = QUEUE_ITEM_LEN;
            memcpy(entry.data, command->valuestring, entry.len);
            queue_try_add(&g_queue, &entry);
        } else {
            printf(" [JSON] unknown type=%s\n", cJSON_IsString(type) ? type->valuestring : "(null)");
        }
        cJSON_Delete(json);
    } else if (len >= 4 && strncmp(msg, "ping", 4) == 0) {
        peer_connection_datachannel_send(g_pc, "pong", 4);
        // TX blink: 100ms x 3
        led_blink_tx();
    }
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
    for (int i = 0; i < 5; i++) {
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);
        sleep_ms(100);
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0);
        sleep_ms(100);
    }
    cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);

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
// Core 1: CYW43 + WiFi + WebRTC (all network on core1)
// cyw43_arch_init() called here so background worker IRQs fire on core1,
// never blocking core0's USB interrupts.
//=============================================================================
static void core1_entry(void) {
    uint32_t now;

    // CYW43 init on core1: background worker binds to THIS core
    if (cyw43_arch_init()) {
        printf("core1: cyw43_arch_init failed\n");
        while (1) { sleep_ms(1000); }
    }

    if (wifi_init() != 0) {
        printf("core1: WiFi init failed\n");
        while (1) { sleep_ms(1000); }
    }

    if (webrtc_init() != 0) {
        printf("core1: WebRTC init failed\n");
        while (1) { sleep_ms(1000); }
    }

    printf("core1: entering WebRTC loop\n");

    while (1) {
        peer_connection_loop(g_pc);

        if (g_state == PEER_CONNECTION_COMPLETED) {
            now = board_millis();

            if ((now - g_dcmsg_time) > 1000) {
                g_dcmsg_time = now;
                char msg[64];
                snprintf(msg, sizeof(msg), "datachannel message: %05d", g_count++);
                peer_connection_datachannel_send(g_pc, msg, strlen(msg));

                if (!g_first_tx_logged) {
                    g_time_first_tx = board_millis();
                    g_first_tx_logged = true;
                    printf("[TIMING] First message TX: %lu ms (from boot)\n", (unsigned long)g_time_first_tx);
                    printf("[TIMING] Time from DataChannel open to first TX: %lu ms\n",
                           (unsigned long)(g_time_first_tx - g_time_datachannel_open));
                }

                led_blink_tx();
            }
        }

        led_blink_loop();
        sleep_us(500);
    }
}

//=============================================================================
// Main loop (Core 0: USB + HID + LED)
//=============================================================================
int main() {
    // Explicit UART setup for RP2350 compatibility
    uart_init(uart0, 115200);
    gpio_set_function(0, GPIO_FUNC_UART);  // TX
    gpio_set_function(1, GPIO_FUNC_UART);  // RX

    stdio_init_all();

    // Wait for serial
    sleep_ms(2000);
    g_time_boot = board_millis();
    printf("\n\n=== RP2040 WebRTC+HID Demo (Dual Core) ===\n");
    printf("[TIMING] Boot complete: %lu ms\n", (unsigned long)g_time_boot);

    queue_init(&g_queue, sizeof(queue_entry_t), QUEUE_SIZE);

    // Launch core1: CYW43 + WiFi + WebRTC
    // cyw43_arch_init() on core1 ensures background worker IRQs
    // fire on core1, keeping core0's USB IRQs unblocked
    printf("Launching core1 for CYW43/WiFi/WebRTC...\n");
    multicore_launch_core1(core1_entry);
    //
    while (1) {
        queue_entry_t itm;
        if (queue_try_remove(&g_queue, &itm)) { break; }
        sleep_ms(100);
    }
    // Core 0: USB only (tud_task must never be blocked)
    board_init();
    irq_set_priority(USBCTRL_IRQ, 0);
    tusb_init();
    //
    while (1) {
        tud_task();
        hid_task();
        tight_loop_contents();
    }
    return 0;
}


static void hid_task(void) {
    queue_entry_t itm;
    static uint32_t start_ms = 0;
    uint32_t now = board_millis();
    if ((now - start_ms) < 10) { return; }
    start_ms = now;
    if (!tud_mounted()) { return; }
    if (!tud_hid_ready()) { return; }
    if (!queue_try_remove(&g_queue, &itm)) { return; }
    if (!itm.len) { return; }

    printf("hid_task: %s (hid_ready=%d)\n", itm.data, tud_hid_ready());

    // Message [0]: {"command":"x,y,z","type":"mouse"}

    int op = 0, dx = 0, dy = 0;
    int ret = sscanf(
        itm.data,
        "%d %d %d",
        &op, &dx, &dy
    );
    if (ret == 3) {
        printf("%d %d %d\n", op, dx, dy);
        if (op || dx || dy) {
            tud_hid_mouse_report(0, (int8_t)op, (int8_t)dx, (int8_t)dy, 0, 0);
        } else if (!op && !dx && !dy) {
            tud_hid_mouse_report(0, 0, 0, 0, 0, 0);
        }
    }
}

uint16_t tud_hid_get_report_cb(uint8_t instance,
    uint8_t report_id,
    hid_report_type_t report_type,
    uint8_t* buffer,
    uint16_t reqlen)
{
    return(0);
}

void tud_hid_set_report_cb(
    uint8_t instance,
    uint8_t report_id,
    hid_report_type_t report_type,
    uint8_t const* buffer,
    uint16_t bufsize)
{
}
