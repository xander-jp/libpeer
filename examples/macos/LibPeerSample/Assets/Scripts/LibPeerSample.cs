using System;
using System.Collections;
using System.Runtime.InteropServices;
using System.Text;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// LibPeer DataChannel Sample - Same functionality as examples/generic/main.c
/// Connect via cloudflared tunnel: cloudflared tunnel --url http://127.0.0.1:8888
/// </summary>
public class LibPeerSample : MonoBehaviour
{
    [Header("Settings")]
    [Tooltip("Signaling URL (e.g., https://xxx.trycloudflare.com)")]
    [SerializeField] private string signalingUrl = "https://";
    [SerializeField] private string signalingPath = "/whip/00/00/00";
    [SerializeField] private string token = "";
    [SerializeField] private float messageInterval = 1.0f;

    [Header("UI")]
    [SerializeField] private InputField urlInputField;
    [SerializeField] private Button connectButton;
    [SerializeField] private Button disconnectButton;
    [SerializeField] private Text statusText;
    [SerializeField] private Text logText;

    private IntPtr _peerConnection = IntPtr.Zero;
    private PeerConnectionState _state = PeerConnectionState.Closed;
    private int _messageCount = 0;
    private float _lastMessageTime = 0f;
    private StringBuilder _logBuilder = new StringBuilder();

    // Prevent callbacks from being garbage collected
    private OnConnectionStateChangeDelegate _onStateChange;
    private OnDataChannelMessageDelegate _onMessage;
    private OnDataChannelOpenDelegate _onOpen;
    private OnDataChannelCloseDelegate _onClose;

    #region Native Bindings

    private const string LIB =
#if UNITY_IOS && !UNITY_EDITOR
        "__Internal";
#else
        "peer";
#endif

    private enum PeerConnectionState
    {
        Closed = 0,
        New = 1,
        Checking = 2,
        Connected = 3,
        Completed = 4,
        Failed = 5,
        Disconnected = 6
    }

    private enum DataChannelType
    {
        None = 0,
        String = 1,
        Binary = 2
    }

    private enum MediaCodec
    {
        None = 0
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct IceServer
    {
        public IntPtr urls;
        public IntPtr username;
        public IntPtr credential;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct PeerConfiguration
    {
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 5)]
        public IceServer[] iceServers;
        public MediaCodec audioCodec;
        public MediaCodec videoCodec;
        public DataChannelType dataChannel;
        public IntPtr onAudioTrack;
        public IntPtr onVideoTrack;
        public IntPtr onRequestKeyframe;
        public IntPtr userData;
    }

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void OnConnectionStateChangeDelegate(PeerConnectionState state, IntPtr userData);

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void OnDataChannelMessageDelegate(IntPtr msg, UIntPtr len, IntPtr userData, ushort sid);

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void OnDataChannelOpenDelegate(IntPtr userData);

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void OnDataChannelCloseDelegate(IntPtr userData);

    [DllImport(LIB, CallingConvention = CallingConvention.Cdecl)]
    private static extern int peer_init();

    [DllImport(LIB, CallingConvention = CallingConvention.Cdecl)]
    private static extern void peer_deinit();

    [DllImport(LIB, CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr peer_connection_create(ref PeerConfiguration config);

    [DllImport(LIB, CallingConvention = CallingConvention.Cdecl)]
    private static extern void peer_connection_destroy(IntPtr pc);

    [DllImport(LIB, CallingConvention = CallingConvention.Cdecl)]
    private static extern int peer_connection_loop(IntPtr pc);

    [DllImport(LIB, CallingConvention = CallingConvention.Cdecl)]
    private static extern void peer_connection_oniceconnectionstatechange(IntPtr pc, OnConnectionStateChangeDelegate callback);

    [DllImport(LIB, CallingConvention = CallingConvention.Cdecl)]
    private static extern void peer_connection_ondatachannel(
        IntPtr pc,
        OnDataChannelMessageDelegate onMessage,
        OnDataChannelOpenDelegate onOpen,
        OnDataChannelCloseDelegate onClose);

    [DllImport(LIB, CallingConvention = CallingConvention.Cdecl)]
    private static extern int peer_connection_datachannel_send(IntPtr pc, byte[] message, UIntPtr len);

    [DllImport(LIB, CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr peer_connection_state_to_string(PeerConnectionState state);

    [DllImport(LIB, CallingConvention = CallingConvention.Cdecl)]
    private static extern int peer_signaling_connect(
        [MarshalAs(UnmanagedType.LPStr)] string url,
        [MarshalAs(UnmanagedType.LPStr)] string token,
        IntPtr pc);

    [DllImport(LIB, CallingConvention = CallingConvention.Cdecl)]
    private static extern void peer_signaling_disconnect();

    [DllImport(LIB, CallingConvention = CallingConvention.Cdecl)]
    private static extern int peer_signaling_loop();

    #endregion

    private void Start()
    {
        // Setup UI
        if (urlInputField != null)
        {
            urlInputField.text = signalingUrl;
        }

        if (connectButton != null)
            connectButton.onClick.AddListener(Connect);

        if (disconnectButton != null)
            disconnectButton.onClick.AddListener(Disconnect);

        UpdateUI();
        Log("LibPeer Sample Ready");
        Log("Enter cloudflared tunnel URL and click Connect");
    }

    private void Update()
    {
        if (_peerConnection == IntPtr.Zero)
            return;

        // Run loops
        peer_connection_loop(_peerConnection);
        peer_signaling_loop();

        // Send periodic messages when connected
        if (_state == PeerConnectionState.Completed)
        {
            if (Time.time - _lastMessageTime >= messageInterval)
            {
                _lastMessageTime = Time.time;
                string msg = $"datachannel message : {_messageCount:D5}";
                SendDataChannelMessage(msg);
                _messageCount++;
            }
        }

        UpdateUI();
    }

    private void OnDestroy()
    {
        Disconnect();
    }

    private void UpdateUI()
    {
        if (statusText != null)
        {
            statusText.text = $"State: {_state}";
        }

        if (connectButton != null)
            connectButton.interactable = _peerConnection == IntPtr.Zero;

        if (disconnectButton != null)
            disconnectButton.interactable = _peerConnection != IntPtr.Zero;

        if (urlInputField != null)
            urlInputField.interactable = _peerConnection == IntPtr.Zero;
    }

    [ContextMenu("Connect")]
    public void Connect()
    {
        if (_peerConnection != IntPtr.Zero)
        {
            Log("Already connected");
            return;
        }

        // Get URL from input field
        if (urlInputField != null)
        {
            signalingUrl = urlInputField.text;
        }

        if (string.IsNullOrEmpty(signalingUrl) || signalingUrl == "https://")
        {
            Log("Please enter signaling URL");
            return;
        }

        // Build full URL with path
        string fullUrl = signalingUrl.TrimEnd('/') + signalingPath;

        Log("Initializing...");
        peer_init();

        // Create callbacks (prevent GC)
        _onStateChange = OnConnectionStateChange;
        _onMessage = OnDataChannelMessage;
        _onOpen = OnDataChannelOpen;
        _onClose = OnDataChannelClose;

        // Setup configuration
        var stunUrl = Marshal.StringToHGlobalAnsi("stun:stun.l.google.com:19302");

        var config = new PeerConfiguration
        {
            iceServers = new IceServer[5],
            audioCodec = MediaCodec.None,
            videoCodec = MediaCodec.None,
            dataChannel = DataChannelType.String,
            onAudioTrack = IntPtr.Zero,
            onVideoTrack = IntPtr.Zero,
            onRequestKeyframe = IntPtr.Zero,
            userData = IntPtr.Zero
        };

        config.iceServers[0] = new IceServer
        {
            urls = stunUrl,
            username = IntPtr.Zero,
            credential = IntPtr.Zero
        };

        Log("Creating peer connection...");
        _peerConnection = peer_connection_create(ref config);

        if (_peerConnection == IntPtr.Zero)
        {
            Log("Failed to create peer connection");
            Marshal.FreeHGlobal(stunUrl);
            return;
        }

        // Set callbacks
        peer_connection_oniceconnectionstatechange(_peerConnection, _onStateChange);
        peer_connection_ondatachannel(_peerConnection, _onMessage, _onOpen, _onClose);

        // Connect to signaling server
        Log($"Connecting to: {fullUrl}");
        int result = peer_signaling_connect(fullUrl, string.IsNullOrEmpty(token) ? null : token, _peerConnection);

        if (result != 0)
        {
            Log($"Failed to connect: {result}");
        }
        else
        {
            Log("Signaling connected");
        }

        Marshal.FreeHGlobal(stunUrl);
    }

    [ContextMenu("Disconnect")]
    public void Disconnect()
    {
        if (_peerConnection == IntPtr.Zero)
            return;

        Log("Disconnecting...");

        peer_signaling_disconnect();
        peer_connection_destroy(_peerConnection);
        peer_deinit();

        _peerConnection = IntPtr.Zero;
        _state = PeerConnectionState.Closed;
        _messageCount = 0;

        Log("Disconnected");
        UpdateUI();
    }

    private void SendDataChannelMessage(string message)
    {
        if (_peerConnection == IntPtr.Zero)
            return;

        byte[] bytes = Encoding.UTF8.GetBytes(message);
        peer_connection_datachannel_send(_peerConnection, bytes, (UIntPtr)bytes.Length);
        Log($"Sent: {message}");
    }

    #region Callbacks

    private void OnConnectionStateChange(PeerConnectionState state, IntPtr userData)
    {
        _state = state;
        string stateStr = Marshal.PtrToStringAnsi(peer_connection_state_to_string(state));
        Log($"State: {stateStr}");
    }

    private void OnDataChannelMessage(IntPtr msg, UIntPtr len, IntPtr userData, ushort sid)
    {
        int length = (int)len.ToUInt32();
        byte[] bytes = new byte[length];
        Marshal.Copy(msg, bytes, 0, length);
        string message = Encoding.UTF8.GetString(bytes);

        Log($"Recv [{sid}]: {message}");

        // Reply pong to ping
        if (message.StartsWith("ping"))
        {
            SendDataChannelMessage("pong");
        }
    }

    private void OnDataChannelOpen(IntPtr userData)
    {
        Log("DataChannel opened");
    }

    private void OnDataChannelClose(IntPtr userData)
    {
        Log("DataChannel closed");
    }

    #endregion

    private void Log(string message)
    {
        string logLine = $"[{DateTime.Now:HH:mm:ss}] {message}";
        Debug.Log($"[LibPeer] {message}");

        _logBuilder.AppendLine(logLine);

        // Keep last 15 lines
        string[] lines = _logBuilder.ToString().Split('\n');
        if (lines.Length > 15)
        {
            _logBuilder.Clear();
            for (int i = lines.Length - 15; i < lines.Length; i++)
            {
                if (!string.IsNullOrEmpty(lines[i]))
                    _logBuilder.AppendLine(lines[i]);
            }
        }

        if (logText != null)
        {
            logText.text = _logBuilder.ToString();
        }
    }
}
