#ifndef MBEDTLS_CONFIG_H
#define MBEDTLS_CONFIG_H

/* Workaround for some mbedtls source files using INT_MAX without including limits.h */
#include <limits.h>

/*============================================================================
 * Memory optimizations for RP2350 (520KB RAM)
 *============================================================================*/
#define MBEDTLS_NO_PLATFORM_ENTROPY
#define MBEDTLS_ENTROPY_HARDWARE_ALT
#define MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_HAVE_TIME

/* Smaller implementations */
#define MBEDTLS_SHA256_SMALLER
#define MBEDTLS_AES_FEWER_TABLES
#define MBEDTLS_AES_ROM_TABLES
#define MBEDTLS_ECP_NIST_OPTIM

/* SSL buffer sizes - RP2350 has enough RAM for full 16KB buffers */
#define MBEDTLS_SSL_MAX_CONTENT_LEN 16384
#define MBEDTLS_SSL_IN_CONTENT_LEN  16384
#define MBEDTLS_SSL_OUT_CONTENT_LEN 4096

/* Reduce MPI (bignum) window size to save RAM */
#define MBEDTLS_MPI_WINDOW_SIZE 2
#define MBEDTLS_MPI_MAX_SIZE 384

/* SSL client and server (server needed for DTLS in WebRTC) */
#define MBEDTLS_SSL_CLI_C
#define MBEDTLS_SSL_SRV_C

/*============================================================================
 * ECC curves - only what Cloudflare/modern servers use
 *============================================================================*/
#define MBEDTLS_ECP_DP_SECP256R1_ENABLED    /* Required for most servers */
#define MBEDTLS_ECP_DP_SECP384R1_ENABLED    /* Fallback */
#define MBEDTLS_ECP_DP_CURVE25519_ENABLED   /* For DTLS/WebRTC */

/*============================================================================
 * Key exchange - ECDHE only (no RSA key exchange, save ~15KB)
 *============================================================================*/
#define MBEDTLS_KEY_EXCHANGE_ECDHE_RSA_ENABLED
#define MBEDTLS_KEY_EXCHANGE_ECDHE_ECDSA_ENABLED

/*============================================================================
 * Ciphers - minimal set for TLS 1.2
 *============================================================================*/
#define MBEDTLS_CIPHER_MODE_CBC
#define MBEDTLS_GCM_C
#define MBEDTLS_AES_C
#define MBEDTLS_CIPHER_C

/*============================================================================
 * Core crypto
 *============================================================================*/
#define MBEDTLS_BIGNUM_C
#define MBEDTLS_CTR_DRBG_C
#define MBEDTLS_ENTROPY_C
#define MBEDTLS_ENTROPY_SHA256_ACCUMULATOR
#define MBEDTLS_MD_C
#define MBEDTLS_SHA1_C
#define MBEDTLS_SHA224_C
#define MBEDTLS_SHA256_C

/* RSA for certificate verification (servers use RSA certs) */
#define MBEDTLS_RSA_C
#define MBEDTLS_PKCS1_V15
#define MBEDTLS_PKCS1_V21

/* ECDSA/ECDH */
#define MBEDTLS_ECDH_C
#define MBEDTLS_ECP_C
#define MBEDTLS_ECDSA_C

/*============================================================================
 * X.509 / Certificates
 *============================================================================*/
#define MBEDTLS_ASN1_PARSE_C
#define MBEDTLS_ASN1_WRITE_C
#define MBEDTLS_OID_C
#define MBEDTLS_PK_C
#define MBEDTLS_PK_PARSE_C
#define MBEDTLS_X509_CRT_PARSE_C
#define MBEDTLS_X509_USE_C
#define MBEDTLS_PEM_PARSE_C
#define MBEDTLS_BASE64_C
#define MBEDTLS_SSL_SERVER_NAME_INDICATION

/*============================================================================
 * TLS 1.2 (for HTTPS signaling)
 *============================================================================*/
#define MBEDTLS_SSL_TLS_C
#define MBEDTLS_SSL_PROTO_TLS1_2
#define MBEDTLS_PLATFORM_C

/*============================================================================
 * DTLS (for WebRTC)
 *============================================================================*/
#define MBEDTLS_SSL_PROTO_DTLS
#define MBEDTLS_SSL_DTLS_SRTP
#define MBEDTLS_SSL_EXPORT_KEYS
#define MBEDTLS_SSL_DTLS_HELLO_VERIFY
#define MBEDTLS_SSL_COOKIE_C
#define MBEDTLS_TIMING_C

/*============================================================================
 * Certificate generation (for DTLS self-signed cert)
 *============================================================================*/
#define MBEDTLS_PEM_WRITE_C
#define MBEDTLS_X509_CRT_WRITE_C
#define MBEDTLS_X509_CREATE_C
#define MBEDTLS_GENPRIME
#define MBEDTLS_PK_WRITE_C

/*============================================================================
 * Misc
 *============================================================================*/
#define MBEDTLS_ERROR_C
/* #define MBEDTLS_DEBUG_C */  /* Disabled: save RAM, enable for debugging */
#define MBEDTLS_SSL_KEEP_PEER_CERTIFICATE /* Required for DTLS fingerprint verification */
#define __unix__

#define MBEDTLS_PLATFORM_MS_TIME_ALT


#endif  // MBEDTLS_CONFIG_H
