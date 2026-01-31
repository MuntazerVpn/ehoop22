def download_content(url, quality, chat_id, msg_id):
    try:
        # إعدادات محسنة لتجنب مشاكل الصيغ
        ydl_opts = {
            'outtmpl': '%(title)s.%(ext)s', 
            'quiet': True, 
            'no_warnings': True,
            # هذا السطر مهم جداً لخداع يوتيوب
            'extractor_args': {'youtube': {'player_client': ['android', 'ios']}},
            # السماح بتحميل أفضل فيديو وصوت ودمجهم، أو أفضل صيغة متاحة
            'format': 'bestvideo+bestaudio/best', 
            'merge_output_format': 'mp4', # دمج الناتج النهائي ليصبح MP4
        }
        
        if quality == 'audio':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]
            })
            text = "جاري تحميل الصوت... 🎵"
        else:
            text = f"جاري تحميل الفيديو... 🚀"

        bot.edit_message_text(text, chat_id, msg_id)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            f = ydl.prepare_filename(info)
            
            # تصحيح اسم الملف في حال تغيرت الصيغة بعد الدمج
            if quality != 'audio':
                pre, ext = os.path.splitext(f)
                if ext != '.mp4':
                    if os.path.exists(pre + '.mp4'):
                        f = pre + '.mp4'
                    elif os.path.exists(pre + '.mkv'): # احتياط
                        f = pre + '.mkv'

            if quality == 'audio': 
                f = os.path.splitext(f)[0] + '.mp3'
                
            return f, info.get('title', 'media')

    except Exception as e:
        bot.edit_message_text(f"خطأ: {str(e)[:100]}", chat_id, msg_id)
        return None, None
