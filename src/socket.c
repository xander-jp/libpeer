#include <errno.h>
#include <string.h>
#include <unistd.h>

#ifdef __RP2040_BM__
// RP2040 bare metal - use lwIP raw API
#include <lwip/udp.h>
#include <lwip/tcp.h>
#include <lwip/pbuf.h>
#include <lwip/ip_addr.h>
#include <lwip/igmp.h>
#include <pico/cyw43_arch.h>
#elif CONFIG_USE_LWIP
#include <lwip/sockets.h>
#include <lwip/igmp.h>
#else
#include <netinet/in.h>
#endif

#include "socket.h"
#include "utils.h"

#ifdef __RP2040_BM__
// RP2040 bare metal UDP socket implementation using lwIP raw API

// UDP receive FIFO
#define UDP_RX_BUF_SIZE 2048
#define UDP_FIFO_SIZE 8

typedef struct {
    uint8_t data[UDP_RX_BUF_SIZE];
    int len;
    ip_addr_t addr;
    u16_t port;
} UdpFifoItem;

typedef struct {
    UdpFifoItem items[UDP_FIFO_SIZE];
    volatile uint16_t read_pos;
    volatile uint16_t write_pos;
} UdpFifo;

static inline void udp_fifo_init(UdpFifo *f) {
    f->read_pos = 0;
    f->write_pos = 0;
}

static inline int udp_fifo_is_empty(const UdpFifo *f) {
    return f->read_pos == f->write_pos;
}

static inline int udp_fifo_is_full(const UdpFifo *f) {
    return ((f->write_pos + 1) % UDP_FIFO_SIZE) == f->read_pos;
}

static inline int udp_fifo_push(UdpFifo *f, const uint8_t *data, int len,
                                 const ip_addr_t *addr, u16_t port) {
    if (udp_fifo_is_full(f)) {
        return 0;
    }
    UdpFifoItem *item = &f->items[f->write_pos];
    if (len > UDP_RX_BUF_SIZE) len = UDP_RX_BUF_SIZE;
    memcpy(item->data, data, len);
    item->len = len;
    item->addr = *addr;
    item->port = port;
    f->write_pos = (f->write_pos + 1) % UDP_FIFO_SIZE;
    return 1;
}

static inline int udp_fifo_pop(UdpFifo *f, UdpFifoItem *out) {
    if (udp_fifo_is_empty(f)) {
        return 0;
    }
    *out = f->items[f->read_pos];
    f->read_pos = (f->read_pos + 1) % UDP_FIFO_SIZE;
    return 1;
}

typedef struct {
    struct udp_pcb *pcb;
    UdpFifo rx_fifo;
} Rp2040UdpSocket;

static void udp_recv_callback(void *arg, struct udp_pcb *pcb, struct pbuf *p,
                               const ip_addr_t *addr, u16_t port) {
    Rp2040UdpSocket *sock = (Rp2040UdpSocket *)arg;
    (void)pcb;

    if (p != NULL) {
        // Copy to temporary buffer then push to FIFO
        uint8_t tmp[UDP_RX_BUF_SIZE];
        int len = p->tot_len;
        if (len > UDP_RX_BUF_SIZE) len = UDP_RX_BUF_SIZE;
        pbuf_copy_partial(p, tmp, len, 0);
        udp_fifo_push(&sock->rx_fifo, tmp, len, addr, port);
        pbuf_free(p);
    }
}

// TCP receive buffer
#define TCP_RX_BUF_SIZE 4096
typedef struct {
    struct tcp_pcb *pcb;
    uint8_t rx_buf[TCP_RX_BUF_SIZE];
    int rx_len;
    int rx_read_pos;
    volatile int connected;
    volatile int error;
} Rp2040TcpSocket;

static err_t tcp_recv_callback(void *arg, struct tcp_pcb *tpcb, struct pbuf *p, err_t err) {
    Rp2040TcpSocket *sock = (Rp2040TcpSocket *)arg;

    if (err != ERR_OK || p == NULL) {
        sock->error = 1;
        return ERR_OK;
    }

    int space = TCP_RX_BUF_SIZE - sock->rx_len;
    int len = p->tot_len;
    if (len > space) len = space;

    if (len > 0) {
        pbuf_copy_partial(p, sock->rx_buf + sock->rx_len, len, 0);
        sock->rx_len += len;
        tcp_recved(tpcb, len);
    }

    pbuf_free(p);
    return ERR_OK;
}

static err_t tcp_connected_callback(void *arg, struct tcp_pcb *tpcb, err_t err) {
    Rp2040TcpSocket *sock = (Rp2040TcpSocket *)arg;
    (void)tpcb;

    if (err == ERR_OK) {
        sock->connected = 1;
    } else {
        sock->error = 1;
    }
    return ERR_OK;
}

static void tcp_error_callback(void *arg, err_t err) {
    Rp2040TcpSocket *sock = (Rp2040TcpSocket *)arg;
    (void)err;
    sock->error = 1;
    sock->pcb = NULL;  // PCB is freed by lwIP on error
}

#endif // __RP2040_BM__

#ifdef __RP2040_BM__
int udp_socket_add_multicast_group(UdpSocket* udp_socket, Address* mcast_addr) {
    // RP2040: Use lwIP IGMP API
    Rp2040UdpSocket *sock = (Rp2040UdpSocket *)udp_socket->priv;
    if (!sock || !sock->pcb) return -1;

    ip4_addr_t mcast_ip;
    mcast_ip.addr = mcast_addr->sin.sin_addr.s_addr;

    err_t err = igmp_joingroup(IP4_ADDR_ANY4, &mcast_ip);
    if (err != ERR_OK) {
        LOGE("Failed to join multicast group: %d", err);
        return -1;
    }
    return 0;
}
#else
int udp_socket_add_multicast_group(UdpSocket* udp_socket, Address* mcast_addr) {
  int ret = 0;
  struct ip_mreq imreq = {0};
  struct in_addr iaddr = {0};

  imreq.imr_interface.s_addr = INADDR_ANY;
  // IPV4 only
  imreq.imr_multiaddr.s_addr = mcast_addr->sin.sin_addr.s_addr;

  if ((ret = setsockopt(udp_socket->fd, IPPROTO_IP, IP_MULTICAST_IF, &iaddr, sizeof(struct in_addr))) < 0) {
    LOGE("Failed to set IP_MULTICAST_IF: %d", ret);
    return ret;
  }

  if ((ret = setsockopt(udp_socket->fd, IPPROTO_IP, IP_ADD_MEMBERSHIP, &imreq, sizeof(struct ip_mreq))) < 0) {
    LOGE("Failed to set IP_ADD_MEMBERSHIP: %d", ret);
    return ret;
  }

  return 0;
}
#endif

#ifdef __RP2040_BM__
int udp_socket_open(UdpSocket* udp_socket, int family, int port) {
    // RP2040: Use lwIP raw UDP API
    static Rp2040UdpSocket rp_sock;  // Static for now - single socket
    memset(&rp_sock, 0, sizeof(rp_sock));
    udp_fifo_init(&rp_sock.rx_fifo);

    udp_socket->bind_addr.family = family;
    udp_socket->priv = &rp_sock;

    cyw43_arch_lwip_begin();

    rp_sock.pcb = udp_new();
    if (!rp_sock.pcb) {
        cyw43_arch_lwip_end();
        LOGE("Failed to create UDP PCB");
        return -1;
    }

    err_t err;
    if (family == AF_INET6) {
        err = udp_bind(rp_sock.pcb, IP6_ADDR_ANY, port);
    } else {
        err = udp_bind(rp_sock.pcb, IP4_ADDR_ANY, port);
    }

    if (err != ERR_OK) {
        udp_remove(rp_sock.pcb);
        rp_sock.pcb = NULL;
        cyw43_arch_lwip_end();
        LOGE("Failed to bind UDP: %d", err);
        return -1;
    }

    udp_recv(rp_sock.pcb, udp_recv_callback, &rp_sock);

    // Get bound port
    udp_socket->bind_addr.port = rp_sock.pcb->local_port;
    udp_socket->fd = 1;  // Dummy fd to indicate socket is open

    cyw43_arch_lwip_end();
    return 0;
}
#else
int udp_socket_open(UdpSocket* udp_socket, int family, int port) {
  int ret;
  int reuse = 1;
  struct sockaddr* sa;
  socklen_t sock_len;

  udp_socket->bind_addr.family = family;
  switch (family) {
    case AF_INET6:
      udp_socket->fd = socket(AF_INET6, SOCK_DGRAM, 0);
      udp_socket->bind_addr.sin6.sin6_family = AF_INET6;
      udp_socket->bind_addr.sin6.sin6_port = htons(port);
      udp_socket->bind_addr.sin6.sin6_addr = in6addr_any;
      udp_socket->bind_addr.port = ntohs(udp_socket->bind_addr.sin6.sin6_port);
      sa = (struct sockaddr*)&udp_socket->bind_addr.sin6;
      sock_len = sizeof(struct sockaddr_in6);
      break;
    case AF_INET:
    default:
      udp_socket->fd = socket(AF_INET, SOCK_DGRAM, 0);
      udp_socket->bind_addr.sin.sin_family = AF_INET;
      udp_socket->bind_addr.sin.sin_port = htons(port);
      udp_socket->bind_addr.sin.sin_addr.s_addr = htonl(INADDR_ANY);
      sa = (struct sockaddr*)&udp_socket->bind_addr.sin;
      sock_len = sizeof(struct sockaddr_in);
      break;
  }

  if (udp_socket->fd < 0) {
    LOGE("Failed to create socket");
    return -1;
  }

  do {
    if ((ret = setsockopt(udp_socket->fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse))) < 0) {
      LOGW("reuse failed. ignore");
    }

    if ((ret = bind(udp_socket->fd, sa, sock_len)) < 0) {
      LOGE("Failed to bind socket: %d", ret);
      break;
    }

    if (getsockname(udp_socket->fd, sa, &sock_len) < 0) {
      LOGE("Get socket info failed");
      break;
    }
  } while (0);

  if (ret < 0) {
    udp_socket_close(udp_socket);
    return -1;
  }

  switch (udp_socket->bind_addr.family) {
    case AF_INET6:
      udp_socket->bind_addr.port = ntohs(udp_socket->bind_addr.sin6.sin6_port);
      break;
    case AF_INET:
    default:
      udp_socket->bind_addr.port = ntohs(udp_socket->bind_addr.sin.sin_port);
      break;
  }

  return 0;
}
#endif

#ifdef __RP2040_BM__
void udp_socket_close(UdpSocket* udp_socket) {
    Rp2040UdpSocket *sock = (Rp2040UdpSocket *)udp_socket->priv;
    if (sock && sock->pcb) {
        cyw43_arch_lwip_begin();
        udp_remove(sock->pcb);
        sock->pcb = NULL;
        cyw43_arch_lwip_end();
    }
    udp_socket->fd = -1;
    udp_socket->priv = NULL;
}
#else
void udp_socket_close(UdpSocket* udp_socket) {
  if (udp_socket->fd > 0) {
    close(udp_socket->fd);
  }
}
#endif

#ifdef __RP2040_BM__
int udp_socket_sendto(UdpSocket* udp_socket, Address* addr, const uint8_t* buf, int len) {
    Rp2040UdpSocket *sock = (Rp2040UdpSocket *)udp_socket->priv;
    if (!sock || !sock->pcb) {
        LOGE("sendto before socket init");
        return -1;
    }

    struct pbuf *p = pbuf_alloc(PBUF_TRANSPORT, len, PBUF_RAM);
    if (!p) {
        LOGE("Failed to allocate pbuf");
        return -1;
    }

    memcpy(p->payload, buf, len);

    ip_addr_t dest_addr;
    u16_t dest_port;

    if (addr->family == AF_INET6) {
        // IPv6
        IP_SET_TYPE(&dest_addr, IPADDR_TYPE_V6);
        memcpy(&dest_addr.u_addr.ip6.addr, &addr->sin6.sin6_addr, 16);
        dest_port = lwip_ntohs(addr->sin6.sin6_port);
    } else {
        // IPv4
        IP_SET_TYPE(&dest_addr, IPADDR_TYPE_V4);
        dest_addr.u_addr.ip4.addr = addr->sin.sin_addr.s_addr;
        dest_port = lwip_ntohs(addr->sin.sin_port);
    }

    cyw43_arch_lwip_begin();
    err_t err = udp_sendto(sock->pcb, p, &dest_addr, dest_port);
    cyw43_arch_lwip_end();

    pbuf_free(p);

    if (err != ERR_OK) {
        LOGE("Failed to sendto: %d", err);
        return -1;
    }

    return len;
}
#else
int udp_socket_sendto(UdpSocket* udp_socket, Address* addr, const uint8_t* buf, int len) {
  struct sockaddr* sa;
  socklen_t sock_len;
  int ret = -1;

  if (udp_socket->fd < 0) {
    LOGE("sendto before socket init");
    return -1;
  }

  switch (addr->family) {
    case AF_INET6:
      addr->sin6.sin6_family = AF_INET6;
      sa = (struct sockaddr*)&addr->sin6;
      sock_len = sizeof(struct sockaddr_in6);
      break;
    case AF_INET:
    default:
      addr->sin.sin_family = AF_INET;
      sa = (struct sockaddr*)&addr->sin;
      sock_len = sizeof(struct sockaddr_in);
      break;
  }

  if ((ret = sendto(udp_socket->fd, buf, len, 0, sa, sock_len)) < 0) {
    LOGE("Failed to sendto: %s", strerror(errno));
    return -1;
  }

  return ret;
}
#endif

#ifdef __RP2040_BM__
int udp_socket_recvfrom(UdpSocket* udp_socket, Address* addr, uint8_t* buf, int len) {
    Rp2040UdpSocket *sock = (Rp2040UdpSocket *)udp_socket->priv;
    if (!sock || !sock->pcb) {
        LOGE("recvfrom before socket init");
        return -1;
    }

    // Poll for data
    cyw43_arch_poll();

    // Pop from FIFO
    UdpFifoItem item;
    if (!udp_fifo_pop(&sock->rx_fifo, &item)) {
        // No data available
        return 0;
    }

    int copy_len = item.len;
    if (copy_len > len) copy_len = len;

    memcpy(buf, item.data, copy_len);

    if (addr) {
        if (IP_IS_V6(&item.addr)) {
            addr->family = AF_INET6;
            memcpy(&addr->sin6.sin6_addr, &item.addr.u_addr.ip6.addr, 16);
            addr->sin6.sin6_port = lwip_htons(item.port);
            addr->port = item.port;
        } else {
            addr->family = AF_INET;
            addr->sin.sin_addr.s_addr = item.addr.u_addr.ip4.addr;
            addr->sin.sin_port = lwip_htons(item.port);
            addr->port = item.port;
        }
    }

    return copy_len;
}
#else
int udp_socket_recvfrom(UdpSocket* udp_socket, Address* addr, uint8_t* buf, int len) {
  struct sockaddr_in6 sin6;
  struct sockaddr_in sin;
  struct sockaddr* sa;
  socklen_t sock_len;
  int ret;

  if (udp_socket->fd < 0) {
    LOGE("recvfrom before socket init");
    return -1;
  }

  switch (udp_socket->bind_addr.family) {
    case AF_INET6:
      sin6.sin6_family = AF_INET6;
      sa = (struct sockaddr*)&sin6;
      sock_len = sizeof(struct sockaddr_in6);
      break;
    case AF_INET:
    default:
      sin.sin_family = AF_INET;
      sa = (struct sockaddr*)&sin;
      sock_len = sizeof(struct sockaddr_in);
      break;
  }

  if ((ret = recvfrom(udp_socket->fd, buf, len, 0, sa, &sock_len)) < 0) {
    LOGE("Failed to recvfrom: %s", strerror(errno));
    return -1;
  }

  if (addr) {
    switch (udp_socket->bind_addr.family) {
      case AF_INET6:
        addr->family = AF_INET6;
        addr->port = htons(sin6.sin6_port);
        memcpy(&addr->sin6, &sin6, sizeof(struct sockaddr_in6));
        break;
      case AF_INET:
      default:
        addr->family = AF_INET;
        addr->port = htons(sin.sin_port);
        memcpy(&addr->sin, &sin, sizeof(struct sockaddr_in));
        break;
    }
  }

  return ret;
}
#endif

#ifdef __RP2040_BM__
int tcp_socket_open(TcpSocket* tcp_socket, int family) {
    static Rp2040TcpSocket rp_sock;
    memset(&rp_sock, 0, sizeof(rp_sock));

    tcp_socket->bind_addr.family = family;
    tcp_socket->priv = &rp_sock;

    cyw43_arch_lwip_begin();

    if (family == AF_INET6) {
        rp_sock.pcb = tcp_new_ip_type(IPADDR_TYPE_V6);
    } else {
        rp_sock.pcb = tcp_new();
    }

    if (!rp_sock.pcb) {
        cyw43_arch_lwip_end();
        LOGE("Failed to create TCP PCB");
        return -1;
    }

    tcp_arg(rp_sock.pcb, &rp_sock);
    tcp_recv(rp_sock.pcb, tcp_recv_callback);
    tcp_err(rp_sock.pcb, tcp_error_callback);

    tcp_socket->fd = 1;  // Dummy fd

    cyw43_arch_lwip_end();
    return 0;
}
#else
int tcp_socket_open(TcpSocket* tcp_socket, int family) {
  tcp_socket->bind_addr.family = family;
  switch (family) {
    case AF_INET6:
      tcp_socket->fd = socket(AF_INET6, SOCK_STREAM, 0);
      break;
    case AF_INET:
    default:
      tcp_socket->fd = socket(AF_INET, SOCK_STREAM, 0);
      break;
  }

  if (tcp_socket->fd < 0) {
    LOGE("Failed to create socket");
    return -1;
  }
  return 0;
}
#endif

#ifdef __RP2040_BM__
int tcp_socket_connect(TcpSocket* tcp_socket, Address* addr) {
    char addr_string[ADDRSTRLEN];
    Rp2040TcpSocket *sock = (Rp2040TcpSocket *)tcp_socket->priv;

    if (!sock || !sock->pcb) {
        LOGE("Connect before socket init");
        return -1;
    }

    addr_to_string(addr, addr_string, sizeof(addr_string));
    LOGI("Connecting to server: %s:%d", addr_string, addr->port);

    ip_addr_t dest_addr;
    u16_t dest_port;

    if (addr->family == AF_INET6) {
        IP_SET_TYPE(&dest_addr, IPADDR_TYPE_V6);
        memcpy(&dest_addr.u_addr.ip6.addr, &addr->sin6.sin6_addr, 16);
        dest_port = lwip_ntohs(addr->sin6.sin6_port);
    } else {
        IP_SET_TYPE(&dest_addr, IPADDR_TYPE_V4);
        dest_addr.u_addr.ip4.addr = addr->sin.sin_addr.s_addr;
        dest_port = lwip_ntohs(addr->sin.sin_port);
    }

    cyw43_arch_lwip_begin();
    err_t err = tcp_connect(sock->pcb, &dest_addr, dest_port, tcp_connected_callback);
    cyw43_arch_lwip_end();

    if (err != ERR_OK) {
        LOGE("Failed to initiate connection: %d", err);
        return -1;
    }

    // Wait for connection (polling)
    int timeout = 10000;  // 10 seconds
    while (!sock->connected && !sock->error && timeout > 0) {
        cyw43_arch_poll();
        sleep_ms(10);
        timeout -= 10;
    }

    if (sock->error || !sock->connected) {
        LOGE("Connection failed or timed out");
        return -1;
    }

    LOGI("Server is connected");
    return 0;
}
#else
int tcp_socket_connect(TcpSocket* tcp_socket, Address* addr) {
  char addr_string[ADDRSTRLEN];
  int ret;
  struct sockaddr* sa;
  socklen_t sock_len;

  if (tcp_socket->fd < 0) {
    LOGE("Connect before socket init");
    return -1;
  }

  switch (addr->family) {
    case AF_INET6:
      addr->sin6.sin6_family = AF_INET6;
      sa = (struct sockaddr*)&addr->sin6;
      sock_len = sizeof(struct sockaddr_in6);
      break;
    case AF_INET:
    default:
      addr->sin.sin_family = AF_INET;
      sa = (struct sockaddr*)&addr->sin;
      sock_len = sizeof(struct sockaddr_in);
      break;
  }

  addr_to_string(addr, addr_string, sizeof(addr_string));
  LOGI("Connecting to server: %s:%d", addr_string, addr->port);
  if ((ret = connect(tcp_socket->fd, sa, sock_len)) < 0) {
    LOGE("Failed to connect to server");
    return -1;
  }

  LOGI("Server is connected");
  return 0;
}
#endif

#ifdef __RP2040_BM__
void tcp_socket_close(TcpSocket* tcp_socket) {
    Rp2040TcpSocket *sock = (Rp2040TcpSocket *)tcp_socket->priv;
    if (sock && sock->pcb) {
        cyw43_arch_lwip_begin();
        tcp_arg(sock->pcb, NULL);
        tcp_recv(sock->pcb, NULL);
        tcp_err(sock->pcb, NULL);
        tcp_close(sock->pcb);
        sock->pcb = NULL;
        cyw43_arch_lwip_end();
    }
    tcp_socket->fd = -1;
    tcp_socket->priv = NULL;
}
#else
void tcp_socket_close(TcpSocket* tcp_socket) {
  if (tcp_socket->fd > 0) {
    close(tcp_socket->fd);
  }
}
#endif

#ifdef __RP2040_BM__
int tcp_socket_send(TcpSocket* tcp_socket, const uint8_t* buf, int len) {
    Rp2040TcpSocket *sock = (Rp2040TcpSocket *)tcp_socket->priv;

    if (!sock || !sock->pcb) {
        LOGE("send before socket init");
        return -1;
    }

    if (sock->error) {
        LOGE("Socket has error");
        return -1;
    }

    cyw43_arch_lwip_begin();

    // Check available send buffer
    u16_t avail = tcp_sndbuf(sock->pcb);
    if (avail == 0) {
        cyw43_arch_lwip_end();
        return 0;  // No space available
    }

    int to_send = len;
    if (to_send > avail) to_send = avail;

    err_t err = tcp_write(sock->pcb, buf, to_send, TCP_WRITE_FLAG_COPY);
    if (err != ERR_OK) {
        cyw43_arch_lwip_end();
        LOGE("Failed to write to TCP: %d", err);
        return -1;
    }

    err = tcp_output(sock->pcb);
    cyw43_arch_lwip_end();

    if (err != ERR_OK) {
        LOGE("Failed to output TCP: %d", err);
        return -1;
    }

    return to_send;
}
#else
int tcp_socket_send(TcpSocket* tcp_socket, const uint8_t* buf, int len) {
  int ret;

  if (tcp_socket->fd < 0) {
    LOGE("sendto before socket init");
    return -1;
  }

  ret = send(tcp_socket->fd, buf, len, 0);
  if (ret < 0) {
    LOGE("Failed to send: %s", strerror(errno));
    return -1;
  }
  return ret;
}
#endif

#ifdef __RP2040_BM__
int tcp_socket_recv(TcpSocket* tcp_socket, uint8_t* buf, int len) {
    Rp2040TcpSocket *sock = (Rp2040TcpSocket *)tcp_socket->priv;

    if (!sock || !sock->pcb) {
        LOGE("recv before socket init");
        return -1;
    }

    if (sock->error) {
        LOGE("Socket has error");
        return -1;
    }

    // Poll for data
    cyw43_arch_poll();

    if (sock->rx_len == 0) {
        return 0;  // No data available
    }

    int copy_len = sock->rx_len - sock->rx_read_pos;
    if (copy_len > len) copy_len = len;

    memcpy(buf, sock->rx_buf + sock->rx_read_pos, copy_len);
    sock->rx_read_pos += copy_len;

    // If all data consumed, reset buffer
    if (sock->rx_read_pos >= sock->rx_len) {
        sock->rx_len = 0;
        sock->rx_read_pos = 0;
    }

    return copy_len;
}
#else
int tcp_socket_recv(TcpSocket* tcp_socket, uint8_t* buf, int len) {
  int ret;

  if (tcp_socket->fd < 0) {
    LOGE("recvfrom before socket init");
    return -1;
  }

  ret = recv(tcp_socket->fd, buf, len, 0);
  if (ret < 0) {
    LOGE("Failed to recv: %s", strerror(errno));
    return -1;
  }
  return ret;
}
#endif
