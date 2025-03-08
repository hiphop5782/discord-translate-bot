# 초대 링크
# https://discord.com/oauth2/authorize?client_id=1347592822051835914&permissions=8&scope=bot

# 토큰 변수

import traceback
import discord
import json
import asyncio
import aiohttp
import io
from discord.ext import commands
from googletrans import Translator

# 번역기 객체 생성
translator = Translator()

# 번역 설정 파일 (채널별 설정 저장)
CONFIG_FILE = "translate_config.json"

# 웹훅 캐싱용 딕셔너리
webhook_cache = {}

# 설정 파일 로드 함수
def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# 설정 파일 저장 함수
def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

# 설정 데이터 로드
config = load_config()

# 디스코드 봇 설정
TOKEN = ""
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True;
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'✅ {bot.user} 봇이 온라인 상태입니다!')

# 언어 설정 명령어
@bot.command()
async def 설정(ctx, lang):
    """
    !설정 [언어코드]
    예시: !설정 en (채널의 모든 메시지를 영어로 번역)
    """
    config[str(ctx.channel.id)] = lang
    save_config(config)
    print(f"✅ 이 채널의 번역 언어가 `{lang}`(으)로 설정되었습니다!");
    await ctx.send(f"✅ 이 채널의 번역 언어가 `{lang}`(으)로 설정되었습니다!")

# **🔹 같은 서버 내에서 같은 이름을 가진 채널 찾기**
def get_channels_by_name(guild, channel_name):
    same_name_channels = []
    for channel in guild.text_channels:
        if channel.name == channel_name:
            same_name_channels.append(channel)
    return same_name_channels

# **🔹 웹훅 가져오기 (캐싱)**
async def get_or_create_webhook(channel):
    if channel.id in webhook_cache:
        return webhook_cache[channel.id]

    webhooks = await channel.webhooks()
    
    if not webhooks:
        webhook = await channel.create_webhook(name="TranslatorBot")
    else:
        webhook = webhooks[0]

    webhook_cache[channel.id] = webhook
    return webhook

# **🔹 웹훅으로 메시지 보내기**
async def send_webhook_message(channel, username, avatar_url, content="", image_urls=[], file_urls=[]):

    webhook = await get_or_create_webhook(channel)

    embeds = []
    for image_url in image_urls[:10]: #디스코드 최대 제한인 10개까지만 추가
        embed = discord.Embed()
        embed.set_image(url=image_url)
        embeds.append(embed)

    files = []
    async with aiohttp.ClientSession() as session:
        for file_url in file_urls[:10]: #디스코드 제한치인 최대 10개까지만 추가
            async with session.get(file_url) as resp:
                if resp.status == 200:
                    file_data = await resp.read()
                    file_name = file_url.split("/")[-1]
                    files.append(discord.File(io.BytesIO(file_data), filename=file_name))

    await webhook.send(
        content if content.strip() else " ", 
        username=username, 
        avatar_url=avatar_url,
        embeds=embeds if embeds else [],
        files=files if files else []
    )

# 메시지 감지 후 자동 번역
@bot.event
async def on_message(message):
    # 봇 자신의 메시지는 무시
    if message.author == bot.user:
        return
    
    # 웹훅 메세지도 무시
    if message.webhook_id is not None:
        return
    
    # 채널이 설정되어 있는지 확인
    original_text = message.content
    source_channel_name = message.channel.name
    source_guild = message.guild  # 현재 서버 정보 가져오기
    same_name_channels = get_channels_by_name(source_guild, source_channel_name)

    print(f"🔹 메세지 수신 : {original_text}")

    # 기존 : 직렬 처리
    # for channel in same_name_channels:
    #     target_channel_id = str(channel.id)

    #     # 자기 자신에게는 보내지 않음
    #     if channel.id == message.channel.id:
    #         continue

    #     # 번역 설정이 있으면 처리
    #     if target_channel_id in config:
    #         target_lang = config[target_channel_id]
    #         try:
    #             translated = translator.translate(message.content, dest=target_lang)

    #             #print(f"**🔄 번역 ({target_lang})**: {translated.text}")
    #             #await channel.send(f"**🔄 번역 ({target_lang})**: {translated.text}")

    #             #웹훅으로 원래 메세지처럼 전송
    #             # 원래 메시지 보낸 사람의 닉네임과 프로필 사진을 사용하여 웹훅으로 메시지 전송
    #             await send_webhook_message(
    #                 channel,
    #                 username=message.author.display_name,
    #                 avatar_url=message.author.avatar.url if message.author.avatar else message.author.default_avatar.url,
    #                 content=f"**{translated.text}**"

    #             )
    #         except Exception as e:
    #             print(f"⚠️ 번역 오류 발생: {e}")
    #             await message.channel.send(f"⚠️ 번역 오류 발생: {e}")

    # 첨부된 이미지 URL 가져오기
    image_urls = []
    file_urls = []
    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image"):
                image_urls.append(attachment.url)
            else:
                file_urls.append(attachment.url)

    # 변경 : 병렬 처리
    async def translate_and_send(channel):
        target_channel_id = str(channel.id)

        # 자기 자신에게는 보내지 않음
        if channel.id == message.channel.id:
            return

        # 번역 설정이 없는 채널이면 무시
        if target_channel_id not in config:
            return  

        target_lang = config[target_channel_id]  # 대상 채널의 번역 언어

        try:
            translated = None
            
            # 텍스트가 있을 경우만 복사
            if original_text:
                translated = translator.translate(original_text, dest=target_lang)

            if translated == None:
                print(f"**🔄 텍스트 없음")
            else:
                print(f"**🔄 번역 ({target_lang})**: {translated.text}")

            # 원래 메시지 보낸 사람의 닉네임과 프로필 사진을 사용하여 웹훅으로 메시지 전송
            await send_webhook_message(
                channel,
                username=message.author.display_name,
                avatar_url=message.author.avatar.url if message.author.avatar else message.author.default_avatar.url,
                content=translated.text if translated else "",

                image_urls=image_urls,
                file_urls=file_urls
            )

        except Exception as e:
            print(f"⚠️ 번역 오류 발생: {e}")
            traceback.print_exc()

    # **🔹 병렬 실행으로 성능 향상**
    await asyncio.gather(*(translate_and_send(channel) for channel in same_name_channels))

    # 봇의 명령어도 정상 작동하도록 추가
    await bot.process_commands(message)

bot.run(TOKEN)
