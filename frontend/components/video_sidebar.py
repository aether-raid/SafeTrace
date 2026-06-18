import streamlit as st
import time

# --------------------------------------------------------------------------- #
# Right Sidebar Component
# --------------------------------------------------------------------------- #
def render_video_sidebar():
    """Renders the video sidebar component and returns file objects for the selected video."""
    
    if "video_library" not in st.session_state:
        st.session_state["video_library"] = []
    if "is_processing" not in st.session_state:
        st.session_state["is_processing"] = False
    if "selected_video_idx" not in st.session_state:
        st.session_state["selected_video_idx"] = 0

    st.markdown("### 🎥 Media Library")

    # Pop-out window for uploading (replaces @st.dialog for compatibility)
    with st.popover("➕ Ingest New Videos", use_container_width=True):
        st.write("Drag and drop your video files below.")
        new_files = st.file_uploader(
            "Upload media",
            type=["mp4", "mov", "avi", "mkv", "webm", "jpg", "png"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        col1, col2 = st.columns(2)
        if col1.button("Upload Files", type="primary", use_container_width=True):
            if new_files:
                if "video_library" not in st.session_state:
                    st.session_state["video_library"] = []
                for f in new_files:
                    st.session_state["video_library"].append({
                        "name": f.name,
                        "size": f.size,
                        "file_obj": f,
                        "status": "processing",
                    })
                st.session_state["is_processing"] = True
                st.rerun()
        if col2.button("Cancel", use_container_width=True):
            st.rerun()

    st.divider()
    st.write("**Uploaded Videos & Status**")

    # --- 1. Handling the Progress Bar ---
    # If files were just uploaded, show a progress bar simulating processing time
    if st.session_state["is_processing"]:
        progress_text = "Processing newly uploaded files..."
        my_bar = st.progress(0, text=progress_text)
        
        # Simulate processing time (replace this with actual saving logic if needed)
        for percent_complete in range(100):
            time.sleep(0.01) 
            my_bar.progress(percent_complete + 1, text=progress_text)
        
        # Update status of all videos to "ready"
        for video in st.session_state["video_library"]:
            video["status"] = "ready"
            
        st.session_state["is_processing"] = False
        my_bar.empty() # Remove progress bar once done
        st.rerun() # Refresh to show updated statuses

    # --- 2. Video Selector ---
    library = st.session_state["video_library"]

    if not library:
        st.info("No media uploaded yet. Click 'Ingest New Videos' to start.")
        return []

    sel_idx = st.session_state["selected_video_idx"]
    if sel_idx >= len(library):
        sel_idx = 0

    video_names = [v["name"] for v in library]
    chosen = st.radio(
        "Select video for analysis",
        video_names,
        index=sel_idx,
        key="video_selector",
    )
    sel_idx = video_names.index(chosen)
    st.session_state["selected_video_idx"] = sel_idx

    selected = library[sel_idx]
    st.info(f"**Selected:** {selected['name']}  \nSize: {selected['size']/(1024*1024):.2f} MB")

    st.divider()

    # --- 3. Displaying the Video List ---
    for idx, video in enumerate(library):
        with st.container(border=True):
            st.markdown(f"**{video['name']}**")
            
            # Display Status and Metadata
            col_meta, col_del = st.columns([3, 1])
            with col_meta:
                size_mb = video['size'] / (1024 * 1024)
                if video['status'] == "ready":
                    st.caption(f"✅ Ready | Size: {size_mb:.2f} MB")
                else:
                    st.caption(f"⏳ Processing... | Size: {size_mb:.2f} MB")
            
            # Delete Button
            with col_del:
                if st.button("🗑️", key=f"del_{idx}", help="Delete video"):
                    deleted_video = st.session_state["video_library"].pop(idx)
                    # Also delete the results if they exist!
                    if deleted_video["name"] in st.session_state.get("results_dict", {}):
                        del st.session_state["results_dict"][deleted_video["name"]]
                    st.rerun()
            
            # Preview Expander
            with st.expander("Preview Media"):
                # Check file type to render image or video
                file_ext = video['name'].split('.')[-1].lower()
                if file_ext in ['jpg', 'jpeg', 'png']:
                    st.image(video['file_obj'], use_column_width=True)
                else:
                    st.video(video['file_obj'])

    # Return only the selected video's file object for analysis
    return [library[st.session_state["selected_video_idx"]]["file_obj"]]