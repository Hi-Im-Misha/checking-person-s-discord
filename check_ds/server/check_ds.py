from fastapi import FastAPI
from pydantic import BaseModel
import aiohttp
import asyncio
from typing import List

app = FastAPI()


class SearchRequest(BaseModel):
    target_user_id: str
    guild_ids: List[str]
    limit: int = 25
    token: str


async def search_user_in_guilds(target_user_id, guild_ids, token, limit=25):
    results = []

    async with aiohttp.ClientSession() as session:
        for guild_id in guild_ids:

            guild_entry = {
                'guild_id': guild_id,
                'guild_name': None,
                'nick': None,
                'roles': [],
                'messages': [], 
                'mentions': [] 
            }

            guild_url = f'https://discord.com/api/v9/guilds/{guild_id}'
            async with session.get(guild_url, headers={'Authorization': token}) as resp:
                guild_data = await resp.json()
                guild_entry['guild_name'] = guild_data.get('name', guild_id)

            print(f'\nИщем в сервере: {guild_entry["guild_name"]} ({guild_id})')

            headers = {'Authorization': token}

            member_url = f'https://discord.com/api/v9/guilds/{guild_id}/members/{target_user_id}'
            async with session.get(member_url, headers=headers) as resp:
                member_data = await resp.json()

                if 'roles' in member_data:
                    role_ids = member_data['roles']
                    guild_entry['nick'] = member_data.get('nick') or member_data['user']['username']
                    print(f'  Ник: {guild_entry["nick"]}')

                    roles_url = f'https://discord.com/api/v9/guilds/{guild_id}/roles'
                    async with session.get(roles_url, headers=headers) as roles_resp:
                        all_roles = await roles_resp.json()

                    roles_map = {role['id']: role['name'] for role in all_roles}
                    guild_entry['roles'] = [roles_map.get(rid, rid) for rid in role_ids]
                    print(f'  Роли: {guild_entry["roles"]}')
                else:
                    print(f'  Ошибка ролей: {member_data}')

            channels_url = f'https://discord.com/api/v9/guilds/{guild_id}/channels'
            async with session.get(channels_url, headers=headers) as resp:
                all_channels = await resp.json()

            if isinstance(all_channels, list):
                channels_map = {ch['id']: ch['name'] for ch in all_channels}
            else:
                print(f'  Ошибка каналов: {all_channels}')
                results.append(guild_entry)
                continue

            search_url = f'https://discord.com/api/v9/guilds/{guild_id}/messages/search'

            author_params = {'author_id': target_user_id, 'limit': limit}
            async with session.get(search_url, params=author_params, headers=headers) as resp:
                data = await resp.json()

                if 'messages' in data:
                    print(f'  Сообщений от пользователя: {data.get("total_results", 0)}')
                    for group in data['messages']:
                        for msg in group:
                            guild_entry['messages'].append({
                                'timestamp': msg['timestamp'],
                                'channel': channels_map.get(msg['channel_id'], msg['channel_id']),
                                'content': msg['content']
                            })
                else:
                    print(f'  Ошибка поиска сообщений: {data}')

            await asyncio.sleep(1)

            mentions_params = {'mentions': target_user_id, 'limit': limit}
            async with session.get(search_url, params=mentions_params, headers=headers) as resp:
                data = await resp.json()

                if 'messages' in data:
                    print(f'  Упоминаний пользователя: {data.get("total_results", 0)}')
                    for group in data['messages']:
                        for msg in group:
                            guild_entry['mentions'].append({
                                'timestamp': msg['timestamp'],
                                'channel': channels_map.get(msg['channel_id'], msg['channel_id']),
                                'content': msg['content'],
                                'author_id': msg['author']['id'],
                                'author_username': msg['author']['username']
                            })
                else:
                    print(f'  Ошибка поиска упоминаний: {data}')

            results.append(guild_entry)
            await asyncio.sleep(1)

    return results


@app.post("/search")
async def search_endpoint(req: SearchRequest):
    results = await search_user_in_guilds(
        req.target_user_id,
        req.guild_ids,
        req.token,
        req.limit
    )
    return {"status": "ok", "results": results}