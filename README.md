# TuneFree_HA - Home Assistant 音乐集成

TuneFree_HA 是一个 Home Assistant 自定义集成，支持多平台音乐搜索、播放和歌词显示。

> 🙏 本项目基于 [TuneFree API](https://api.tunefree.fun/) 服务，感谢 API 作者的无私分享！
> 
> 详情请参阅：[Linux.do 论坛讨论](https://linux.do/t/topic/1326425)

## 功能特性

- 🎵 多平台音乐搜索（网易云、QQ音乐、酷我）
- 📋 支持播放歌单、榜单
- 🎤 实时歌词同步滚动
- 🎨 精美歌词卡片组件
- 🔀 随机播放支持
- 📱 响应式设计，适配竖屏/横屏

## 安装

### HACS 一键安装（推荐）

[![Open your Home Assistant instance and open TuneFree inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JochenZhou&repository=tunefree_ha&category=integration)

### HACS 手动添加

1. 在 HACS 中点击右上角菜单，选择「自定义存储库」
2. 添加仓库地址：`https://github.com/JochenZhou/tunefree_ha`
3. 类别选择「Integration」
4. 点击添加，然后搜索 TuneFree 安装
5. 重启 Home Assistant

### 手动安装

1. 将 `tunefree` 文件夹复制到 `custom_components` 目录
2. 重启 Home Assistant
3. 在集成页面添加 TuneFree
4. 配置 API 地址和目标播放器

## 配置

| 参数 | 说明 | 必填 |
|------|------|------|
| API URL | TuneFree API 服务地址 | 是 |
| 默认音乐源 | netease/qq/kuwo | 否 |
| 目标播放器 | 用于播放的媒体播放器实体 | 否 |

### 导入歌单

1. 进入 Home Assistant 设置 → 设备与服务 → TuneFree
2. 点击「配置」按钮
3. 选择音乐源（网易云/QQ音乐/酷我）
4. 输入歌单 ID（从歌单链接中获取）
5. 点击提交，歌单将出现在媒体浏览器中

## 服务

### tunefree.play_music
搜索并播放单首音乐

```yaml
service: tunefree.play_music
data:
  keyword: "歌曲名"
  entity_id: media_player.xxx
  source: netease  # 可选
```

### tunefree.play_playlist
播放歌单

```yaml
service: tunefree.play_playlist
data:
  playlist_id: "123456789"
  entity_id: media_player.xxx
  source: netease
  shuffle: false
```

### tunefree.play_toplist
播放榜单

```yaml
service: tunefree.play_toplist
data:
  toplist_id: "榜单ID"
  entity_id: media_player.xxx
  source: netease
  shuffle: false
```

### tunefree.play_search_list
搜索并播放多首歌曲

```yaml
service: tunefree.play_search_list
data:
  keyword: "关键词"
  entity_id: media_player.xxx
  limit: 20
  shuffle: true
```

### tunefree.search_music
搜索音乐（返回结果，供 AI/MCP 使用）

```yaml
service: tunefree.search_music
data:
  keyword: "关键词"
  limit: 10
  source: all
```

### tunefree.get_lyrics
获取歌词

```yaml
service: tunefree.get_lyrics
data:
  song_id: "歌曲ID"
  source: netease
```

## 歌词卡片



### 卡片配置

```yaml
type: custom:tunefree-lyrics-card
entity: media_player.tunefree_service_tunefree_player
show_controls: true
card_height: 400
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| entity | TuneFree 媒体播放器实体 | 必填 |
| show_controls | 显示播放控制按钮 | true |
| card_height | 卡片高度(px) | 400 |

### 功能

- 歌词实时同步滚动
- 当前歌词行高亮显示
- 播放/暂停/上一曲/下一曲控制
- 竖屏自适应布局
- 模糊背景封面

## 传感器

集成会创建以下传感器：

- `sensor.tunefree_service_current_song` - 当前播放歌曲信息

## 许可证

MIT License
## 致谢

- API 服务：[TuneFree API](https://api.tunefree.fun/)