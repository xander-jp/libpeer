rm -rf ./snapshots/*.jpg
scp -q -r pi@192.168.124.32:/home/pi/git/libpeer/examples/hid-usb/scene-detect/snapshots ./.

source venv312/bin/activate
python ./train_onnx.py

scp -q ./scene_labels.json pi@192.168.124.32:/home/pi/git/libpeer/examples/hid-usb/scene-detect/.
scp -q ./scene_model.onnx pi@192.168.124.32:/home/pi/git/libpeer/examples/hid-usb/scene-detect/.


