from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager

async def get_current_media():
    try:
        mgr = await MediaManager.request_async()
        session = mgr.get_current_session()  # get active session
        if session:
            info = await session.try_get_media_properties_async()
            title = info.title if info.title else "-"
            artist = info.artist if info.artist else "-"

            playback_info = session.get_playback_info()
            status_map = {
                0: "Closed",
                1: "Opened",
                2: "Changing",
                3: "Stopped",
                4: "Playing",
                5: "Paused"
            }
            status = status_map.get(playback_info.playback_status, "Unknown")
            is_playing = playback_info.playback_status == 4

            return title, artist, status, is_playing

        return "-", "-", "No session", False
    except Exception as e:
        print(f"[ERROR] get_current_media exception: {e}")
        return "-", "-", "Error", False
    
async def safe_get_current_media():
    try:
        return await get_current_media()
    except Exception as e:
        print(f"[WARN] get_current_media failed: {e}")
        return "-", "-", None, False
