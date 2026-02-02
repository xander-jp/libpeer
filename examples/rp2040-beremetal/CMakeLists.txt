CMAKE_MINIMUM_REQUIRED(VERSION 3.12)

# Apply patches to third-party libraries (only once)
set(PATCH_MARKER "${CMAKE_CURRENT_LIST_DIR}/.patches_applied")
if(NOT EXISTS ${PATCH_MARKER})
  message(STATUS "Applying patches to third-party libraries...")
  execute_process(
    COMMAND patch -p1 --forward -i ${CMAKE_CURRENT_LIST_DIR}/libsrtp.patch
    WORKING_DIRECTORY ${CMAKE_CURRENT_LIST_DIR}/../../third_party/libsrtp
    RESULT_VARIABLE LIBSRTP_PATCH_RESULT
  )
  execute_process(
    COMMAND patch -p1 --forward -i ${CMAKE_CURRENT_LIST_DIR}/mbedtls.patch
    WORKING_DIRECTORY ${CMAKE_CURRENT_LIST_DIR}/../../third_party/mbedtls
    RESULT_VARIABLE MBEDTLS_PATCH_RESULT
  )
  execute_process(
    COMMAND patch -p1 --forward -i ${CMAKE_CURRENT_LIST_DIR}/usrsctp.patch
    WORKING_DIRECTORY ${CMAKE_CURRENT_LIST_DIR}/../../third_party/usrsctp
    RESULT_VARIABLE USRSCTP_PATCH_RESULT
  )
  file(WRITE ${PATCH_MARKER} "Patches applied at ${CMAKE_CURRENT_LIST_DIR}")
  message(STATUS "Patches applied successfully")
endif()

SET(PRJ rp2040bm)
SET(PICO_BOARD pico_w)
SET(HOME $ENV{HOME})
SET(PICO_SDK_FETCH_FROM_GIT on)
INCLUDE(pico_sdk_import.cmake)

PROJECT(${PRJ} C CXX ASM)
SET(CMAKE_C_STANDARD 11)
SET(CMAKE_CXX_STANDARD 17)

# pico_sdk_init must be called early, right after project()
pico_sdk_init()
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O0 -g -include stdint.h -include stddef.h")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -O0 -g -include stdint.h -include stddef.h")

# libsrtp: use standard integer types
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DHAVE_STDINT_H -DHAVE_UINT8_T -DHAVE_UINT16_T -DHAVE_UINT32_T -DHAVE_INT32_T -DHAVE_UINT64_T")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DHAVE_STDINT_H -DHAVE_UINT8_T -DHAVE_UINT16_T -DHAVE_UINT32_T -DHAVE_INT32_T -DHAVE_UINT64_T")
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DHAVE_NETINET_IN_H")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DHAVE_NETINET_IN_H")
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Dbe32_to_cpu=lwip_ntohl")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -Dbe32_to_cpu=lwip_ntohl")
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Dbe64_to_cpu=__builtin_bswap64")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -Dbe64_to_cpu=__builtin_bswap64")
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DHAVE_STDLIB_H")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DHAVE_STDLIB_H")
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DPACKAGE_STRING=\\\"libsrtp2\\\" -DPACKAGE_VERSION=\\\"2.0.0\\\"")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DPACKAGE_STRING=\\\"libsrtp2\\\" -DPACKAGE_VERSION=\\\"2.0.0\\\"")

IF (PICO_SDK_VERSION_STRING VERSION_LESS "1.3.0")
    message(FATAL_ERROR "Raspberry Pi Pico SDK version 1.3.0 (or later) required. Your version is ${PICO_SDK_VERSION_STRING}")
ENDIF()
SET(CMAKE_INCLUDE_CURRENT_DIR ON)

SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -D__RP2040_BM__")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -D__RP2040_BM__")

# Don't define CONFIG_USE_LWIP - use POSIX socket stubs instead
# SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DCONFIG_USE_LWIP=1")
# SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DCONFIG_USE_LWIP=1")

# Use mbedtls 2.x API (Pico SDK uses mbedtls 2.x)
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DCONFIG_MBEDTLS_2_X=1")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DCONFIG_MBEDTLS_2_X=1")

# libsrtp: use mbedtls for AES and define CPU type
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DMBEDTLS")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DMBEDTLS")
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DCPU_RISC")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DCPU_RISC")

# RP2040 is little-endian ARM Cortex-M0+
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -D__LITTLE_ENDIAN=1234 -D__BIG_ENDIAN=4321 -D__BYTE_ORDER=__LITTLE_ENDIAN")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -D__LITTLE_ENDIAN=1234 -D__BIG_ENDIAN=4321 -D__BYTE_ORDER=__LITTLE_ENDIAN")

# usrsctp defines
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DSCTP_SIMPLE_ALLOCATOR -DSCTP_PROCESS_LEVEL_LOCKS -D__Userspace__")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DSCTP_SIMPLE_ALLOCATOR -DSCTP_PROCESS_LEVEL_LOCKS -D__Userspace__")
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DERESTART=85")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DERESTART=85")


SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DHTTP_DO_NOT_USE_CUSTOM_CONFIG")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DHTTP_DO_NOT_USE_CUSTOM_CONFIG")
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DDMQTT_DO_NOT_USE_CUSTOM_CONFIG")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DMQTT_DO_NOT_USE_CUSTOM_CONFIG")


IF (OLD_SRM)
  SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -D__OLD_SRM__")
  MESSAGE(">> OLD SRM mode")
ELSE()
  MESSAGE(">> Stages Mode")
ENDIF()


# SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -D__DRIVER_INFO__ -D__DRIVER_DEBUG__")
# SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -D__DRIVER_INFO__ -D__DRIVER_DEBUG__")
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -D__DRIVER_INFO__")
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -D__DRIVER_INFO__")

INCLUDE_DIRECTORIES(".")


INCLUDE(${CMAKE_CURRENT_LIST_DIR}/../../third_party/coreHTTP/httpFilePaths.cmake)
INCLUDE(${CMAKE_CURRENT_LIST_DIR}/../../third_party/coreMQTT/mqttFilePaths.cmake)
INCLUDE_DIRECTORIES(
  ${CMAKE_CURRENT_LIST_DIR}/
  ${CMAKE_CURRENT_LIST_DIR}/inc/
  ${CMAKE_BINARY_DIR}/
  ${CMAKE_CURRENT_LIST_DIR}/../../third_party/libsrtp/include/
  ${CMAKE_CURRENT_LIST_DIR}/../../third_party/libsrtp/crypto/include/
  ${CMAKE_CURRENT_LIST_DIR}/../../third_party/cJSON/
  ${CMAKE_CURRENT_LIST_DIR}/../../third_party/usrsctp/usrsctplib/
  ${CMAKE_CURRENT_LIST_DIR}/../../src/
  ${HTTP_INCLUDE_PUBLIC_DIRS}
  ${MQTT_INCLUDE_PUBLIC_DIRS}
)

FILE(GLOB C_SOURCE_FILES ../../src/*.c)
# Build libsrtp
file(GLOB LIBSRC
  ../../third_party/libsrtp/srtp/srtp.c
  ../../third_party/libsrtp/crypto/cipher/cipher.c
  ../../third_party/libsrtp/crypto/cipher/null_cipher.c
  ../../third_party/libsrtp/crypto/cipher/aes.c
  ../../third_party/libsrtp/crypto/cipher/aes_icm.c
  ../../third_party/libsrtp/crypto/cipher/cipher_test_cases.c
  ../../third_party/libsrtp/crypto/hash/auth.c
  ../../third_party/libsrtp/crypto/hash/null_auth.c
  ../../third_party/libsrtp/crypto/hash/hmac.c
  ../../third_party/libsrtp/crypto/hash/sha1.c
  ../../third_party/libsrtp/crypto/hash/auth_test_cases.c
  ../../third_party/libsrtp/crypto/kernel/alloc.c
  ../../third_party/libsrtp/crypto/kernel/crypto_kernel.c
  ../../third_party/libsrtp/crypto/kernel/err.c
  ../../third_party/libsrtp/crypto/kernel/key.c
  ../../third_party/libsrtp/crypto/math/datatypes.c
  ../../third_party/libsrtp/crypto/math/stat.c
  ../../third_party/libsrtp/crypto/replay/rdb.c
  ../../third_party/libsrtp/crypto/replay/rdbx.c
  ../../third_party/libsrtp/crypto/replay/ut_sim.c
  # cJSON
  ../../third_party/cJSON/cJSON.c
  # usrsctp (nothreads mode - no user_recv_thread.c)
  ../../third_party/usrsctp/usrsctplib/user_environment.c
  ../../third_party/usrsctp/usrsctplib/user_mbuf.c
  ../../third_party/usrsctp/usrsctplib/user_socket.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_asconf.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_auth.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_bsd_addr.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_callout.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_cc_functions.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_crc32.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_indata.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_input.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_output.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_pcb.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_peeloff.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_sha1.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_ss_functions.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_sysctl.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_timer.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_userspace.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctp_usrreq.c
  ../../third_party/usrsctp/usrsctplib/netinet/sctputil.c
)

ADD_EXECUTABLE(
    ${PRJ}
    ${C_SOURCE_FILES}
    ${LIBSRC}
    ${HTTP_SOURCES}
    ${CMAKE_CURRENT_LIST_DIR}/atomic_compat.c
    ${CMAKE_CURRENT_LIST_DIR}/inet_compat.c
    ${CMAKE_CURRENT_LIST_DIR}/main.c
)
FILE(MAKE_DIRECTORY ${CMAKE_BINARY_DIR}/srtp2/)
FILE(COPY ${CMAKE_CURRENT_LIST_DIR}/../../third_party/libsrtp/include/srtp.h
    DESTINATION ${CMAKE_BINARY_DIR}/srtp2/)

PROJECT(${PRJ} VERSION 1.0.0)

TARGET_LINK_LIBRARIES(
    ${PRJ}
    pico_stdlib
    hardware_spi
    hardware_i2c
    tinyusb_host
    tinyusb_device
    tinyusb_board
    pico_cyw43_arch_lwip_threadsafe_background
    # pico_cyw43_arch_lwip_poll
    pico_mbedtls
)

pico_enable_stdio_usb(${PRJ} 0)
pico_enable_stdio_uart(${PRJ} 1)
pico_add_extra_outputs(${PRJ})

ADD_COMPILE_OPTIONS(
    -Wall
    -Wno-format          # int != int32_t as far as the compiler is concerned because gcc has int32_t as long int
    -Wno-unused-function # we have some for the docs that aren't called
    -Wno-maybe-uninitialized
)
