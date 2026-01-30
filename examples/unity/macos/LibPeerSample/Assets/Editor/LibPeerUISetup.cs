using UnityEngine;
using UnityEngine.UI;
using UnityEditor;

public class LibPeerUISetup : Editor
{
    [MenuItem("Tools/LibPeer/Setup UI")]
    public static void SetupUI()
    {
        // Find LibPeerSample component
        var libPeerSample = FindObjectOfType<LibPeerSample>();
        if (libPeerSample == null)
        {
            Debug.LogError("LibPeerSample component not found in scene!");
            return;
        }

        // Delete existing Canvas
        var existingCanvas = GameObject.Find("Canvas");
        if (existingCanvas != null)
        {
            DestroyImmediate(existingCanvas);
            Debug.Log("Deleted existing Canvas");
        }

        // Delete existing EventSystem
        var existingEventSystem = GameObject.Find("EventSystem");
        if (existingEventSystem != null)
        {
            DestroyImmediate(existingEventSystem);
            Debug.Log("Deleted existing EventSystem");
        }

        // Create Canvas
        var canvasGO = new GameObject("Canvas");
        var canvas = canvasGO.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;

        var scaler = canvasGO.AddComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1920, 1080);
        scaler.matchWidthOrHeight = 0.5f;

        canvasGO.AddComponent<GraphicRaycaster>();

        // Create EventSystem if not exists
        if (FindObjectOfType<UnityEngine.EventSystems.EventSystem>() == null)
        {
            var eventSystemGO = new GameObject("EventSystem");
            eventSystemGO.AddComponent<UnityEngine.EventSystems.EventSystem>();
            eventSystemGO.AddComponent<UnityEngine.EventSystems.StandaloneInputModule>();
        }

        // Create URL Input Field
        var inputFieldGO = CreateInputField(canvasGO.transform, "UrlInputField",
            new Vector2(0, -50), new Vector2(600, 40), "Enter Signaling URL...");
        var inputField = inputFieldGO.GetComponent<InputField>();
        inputField.text = "https://";

        // Create Connect Button
        var connectBtnGO = CreateButton(canvasGO.transform, "ConnectButton",
            new Vector2(-110, -100), new Vector2(200, 40), "Connect",
            new Color(0.2f, 0.6f, 0.2f, 1f));
        var connectBtn = connectBtnGO.GetComponent<Button>();

        // Create Disconnect Button
        var disconnectBtnGO = CreateButton(canvasGO.transform, "DisconnectButton",
            new Vector2(110, -100), new Vector2(200, 40), "Disconnect",
            new Color(0.6f, 0.2f, 0.2f, 1f));
        var disconnectBtn = disconnectBtnGO.GetComponent<Button>();

        // Create Status Text
        var statusTextGO = CreateText(canvasGO.transform, "StatusText",
            new Vector2(0, -150), new Vector2(400, 30), "State: Closed", 22, TextAnchor.MiddleCenter);
        var statusText = statusTextGO.GetComponent<Text>();

        // Create Log Text (anchored to top, below status text)
        var logTextGO = CreateLogText(canvasGO.transform, "LogText",
            new Vector2(0, -180), new Vector2(-40, 800), "", 24);
        var logText = logTextGO.GetComponent<Text>();
        logText.color = new Color(0.9f, 0.9f, 0.9f, 1f);

        // Assign to LibPeerSample
        var serializedObject = new SerializedObject(libPeerSample);
        serializedObject.FindProperty("urlInputField").objectReferenceValue = inputField;
        serializedObject.FindProperty("connectButton").objectReferenceValue = connectBtn;
        serializedObject.FindProperty("disconnectButton").objectReferenceValue = disconnectBtn;
        serializedObject.FindProperty("statusText").objectReferenceValue = statusText;
        serializedObject.FindProperty("logText").objectReferenceValue = logText;
        serializedObject.ApplyModifiedProperties();

        Debug.Log("LibPeer UI setup complete!");
        EditorUtility.SetDirty(libPeerSample);
    }

    static GameObject CreateInputField(Transform parent, string name, Vector2 position, Vector2 size, string placeholder)
    {
        var go = new GameObject(name);
        go.transform.SetParent(parent, false);

        var rect = go.AddComponent<RectTransform>();
        rect.anchorMin = new Vector2(0.5f, 1f);
        rect.anchorMax = new Vector2(0.5f, 1f);
        rect.anchoredPosition = position;
        rect.sizeDelta = size;

        var image = go.AddComponent<Image>();
        image.color = Color.white;

        var inputField = go.AddComponent<InputField>();

        // Create Text child
        var textGO = new GameObject("Text");
        textGO.transform.SetParent(go.transform, false);
        var textRect = textGO.AddComponent<RectTransform>();
        textRect.anchorMin = Vector2.zero;
        textRect.anchorMax = Vector2.one;
        textRect.offsetMin = new Vector2(10, 5);
        textRect.offsetMax = new Vector2(-10, -5);
        var text = textGO.AddComponent<Text>();
        text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        text.fontSize = 20;
        text.color = Color.black;
        text.supportRichText = false;
        text.alignment = TextAnchor.MiddleLeft;
        inputField.textComponent = text;

        // Create Placeholder child
        var placeholderGO = new GameObject("Placeholder");
        placeholderGO.transform.SetParent(go.transform, false);
        var phRect = placeholderGO.AddComponent<RectTransform>();
        phRect.anchorMin = Vector2.zero;
        phRect.anchorMax = Vector2.one;
        phRect.offsetMin = new Vector2(10, 5);
        phRect.offsetMax = new Vector2(-10, -5);
        var phText = placeholderGO.AddComponent<Text>();
        phText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        phText.fontSize = 20;
        phText.fontStyle = FontStyle.Italic;
        phText.color = new Color(0.2f, 0.2f, 0.2f, 0.5f);
        phText.text = placeholder;
        phText.alignment = TextAnchor.MiddleLeft;
        inputField.placeholder = phText;

        return go;
    }

    static GameObject CreateButton(Transform parent, string name, Vector2 position, Vector2 size, string label, Color color)
    {
        var go = new GameObject(name);
        go.transform.SetParent(parent, false);

        var rect = go.AddComponent<RectTransform>();
        rect.anchorMin = new Vector2(0.5f, 1f);
        rect.anchorMax = new Vector2(0.5f, 1f);
        rect.anchoredPosition = position;
        rect.sizeDelta = size;

        var image = go.AddComponent<Image>();
        image.color = color;

        var button = go.AddComponent<Button>();
        button.targetGraphic = image;

        // Create Text child
        var textGO = new GameObject("Text");
        textGO.transform.SetParent(go.transform, false);
        var textRect = textGO.AddComponent<RectTransform>();
        textRect.anchorMin = Vector2.zero;
        textRect.anchorMax = Vector2.one;
        textRect.offsetMin = Vector2.zero;
        textRect.offsetMax = Vector2.zero;
        var text = textGO.AddComponent<Text>();
        text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        text.fontSize = 24;
        text.fontStyle = FontStyle.Bold;
        text.color = Color.white;
        text.text = label;
        text.alignment = TextAnchor.MiddleCenter;

        return go;
    }

    static GameObject CreateText(Transform parent, string name, Vector2 position, Vector2 size, string content, int fontSize, TextAnchor alignment, bool stretchWidth = false)
    {
        var go = new GameObject(name);
        go.transform.SetParent(parent, false);

        var rect = go.AddComponent<RectTransform>();
        if (stretchWidth)
        {
            rect.anchorMin = new Vector2(0f, 0f);
            rect.anchorMax = new Vector2(1f, 0f);
            rect.anchoredPosition = position;
            rect.sizeDelta = size;
        }
        else
        {
            rect.anchorMin = new Vector2(0.5f, 1f);
            rect.anchorMax = new Vector2(0.5f, 1f);
            rect.anchoredPosition = position;
            rect.sizeDelta = size;
        }

        var text = go.AddComponent<Text>();
        text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        text.fontSize = fontSize;
        text.color = Color.white;
        text.text = content;
        text.alignment = alignment;

        return go;
    }

    static GameObject CreateLogText(Transform parent, string name, Vector2 position, Vector2 size, string content, int fontSize)
    {
        var go = new GameObject(name);
        go.transform.SetParent(parent, false);

        var rect = go.AddComponent<RectTransform>();
        // Anchor to top, stretch width
        rect.anchorMin = new Vector2(0f, 1f);
        rect.anchorMax = new Vector2(1f, 1f);
        rect.pivot = new Vector2(0.5f, 1f);
        rect.anchoredPosition = position;
        rect.sizeDelta = size;

        var text = go.AddComponent<Text>();
        text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        text.fontSize = fontSize;
        text.color = Color.white;
        text.text = content;
        text.alignment = TextAnchor.UpperLeft;
        text.verticalOverflow = VerticalWrapMode.Overflow;

        return go;
    }
}
