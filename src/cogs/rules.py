import re
import time
import traceback

from discord.ext import commands
import discord

from src import config as conf

class RulesEnforcer(commands.Cog, name="Rules"):
    def __init__(self, bot):
        self.bot = bot

        # Maps channel : list of deleted messages
        self._deleted = {}

        self._recent_joins = []

        self.massjoin_detect = True
        self.massjoin_active = False

        bot.loop.create_task(self._update_rules())

    @commands.command()
    async def rule(self, ctx, number):
        """Display a rule"""
        if self._rules.get(number) is None:
            return await ctx.send(f"Invalid rule number: `{discord.utils.escape_mentions(number)}`")
        else:
            await ctx.send(f"**Rule {number}**:\n{self._rules[number]}")

    @commands.command()
    async def snipe(self, ctx, number = None):
        if ctx.channel not in self._deleted:
            return await ctx.send("No message to snipe.")

        messages = self._deleted[ctx.channel]
        index = abs(int(number)) if number else 0

        if index >= len(messages):
            return await ctx.send(f"The bot currently has only {len(messages)} deleted messages stored "
                + "with index 0 being the most recently deleted message")

        message = self._deleted[ctx.channel][len(messages) - 1 - index]
        user = str(message.author)
        ts = message.created_at.isoformat(" ")
        content = message.content
        return await ctx.send(f"**{discord.utils.escape_markdown(discord.utils.escape_mentions(user))}** said on {ts} UTC:\n{content}")

    async def _notify_staff(self, guild, message):
        role = conf.staff_role

        channel = guild.system_channel
        if channel:
            return await channel.send(f"<@&{role}> {message}")

    def _chunk_message(self, msg):
        messages = []
        while len(msg) > conf.max_msg_size:
            chunk = msg[:conf.max_msg_size]

            end_index = chunk.rfind('\n')
            if end_index == -1:
                end_index = conf.max_msg_size

            messages.append(chunk[:end_index])
            msg = msg[end_index + 1:]

        messages.append(msg)
        return messages

    async def _reply_chunks(self, reply, msgs):
        for msg in msgs:
            reply = await reply.reply(msg)

        return reply

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not self.massjoin_detect:
            return

        current_time = time.time()

        if not self.massjoin_active:
            self._recent_joins = [
                x for x in self._recent_joins
                if current_time - x["join_time"] <= conf.massjoin_window
            ]

        is_bot_pfp = member.default_avatar_url == member.avatar_url if conf.massjoin_default_pfp else True

        is_bot_age = ( current_time - member.created_at.timestamp() < conf.massjoin_min_acc_age_val
                if conf.massjoin_min_acc_age else True )

        self._recent_joins.append({
            "join_time": current_time,
            "id": member.id,
            "assumed_bot": is_bot_pfp and is_bot_age
        })


        join_amount = len(self._recent_joins)

        if join_amount >= conf.massjoin_amount and not self.massjoin_active:
            try:
                self.massjoin_active = True

                msg = await self._notify_staff(member.guild,
                    f"Mass member join detected. React with {conf.yes_react} to take action "
                    + f"or with {conf.no_react} to ignore")

                await msg.add_reaction(conf.no_react)
                await msg.add_reaction(conf.yes_react)

                def _check(reaction, user, reaction_msg):
                    return ( reaction.message.id == reaction_msg.id
                        and any(role.id == conf.staff_role for role in user.roles)
                        and user.id != self.bot.user.id )

                reaction, user = await self.bot.wait_for('reaction_add',
                    check=lambda reaction, user: _check(reaction, user, msg),
                    timeout=conf.massjoin_notif_timeout)

                if reaction.emoji == conf.no_react:
                    await msg.reply("Not taking any action and resetting the join detection")

                if reaction.emoji == conf.yes_react:
                    wizard_msg = ( "Users assumed to be bots:\n" + ",\n".join(map(lambda x: f"<@{x['id']}>",
                        filter(lambda x: x["assumed_bot"], self._recent_joins)))
                        + "\nUsers assumed to not be bots:\n" + ",\n".join(map(lambda x: f"<@{x['id']}>",
                        filter(lambda x: not x["assumed_bot"], self._recent_joins))) )


                    reply = await self._reply_chunks(msg, self._chunk_message(wizard_msg))

                    await reply.add_reaction(conf.no_react)
                    await reply.add_reaction(conf.yes_react)

                    reaction, user = await self.bot.wait_for('reaction_add',
                        check=lambda reaction, user: _check(reaction, user, reply),
                        timeout=conf.massjoin_wizard_timeout)

                    if reaction.emoji == conf.no_react:
                        await reply.reply("Not banning any users and resetting the join detection")

                    if reaction.emoji == conf.yes_react:
                        bot_count = sum(1 for x in self._recent_joins if x['assumed_bot'])
                        ban_start_msg = await reply.reply(f"Banning {bot_count} user(s)")

                        failed_bans = []
                        for user in self._recent_joins:
                            if not user["assumed_bot"]:
                                continue

                            try:
                                await member.guild.ban(discord.Object(id=user["id"]))

                            except:
                                failed_bans.append(user["id"])
                                await ban_start_msg.reply("Banning failed with the following exception:\n"
                                    + f"```py\n{traceback.format_exc()}\n```")

                        await self._reply_chunks(
                            ban_start_msg,
                            self._chunk_message("Banned all bots except:\n"
                                + ",\n".join(map(lambda x: f"<@{x}>", failed_bans))))

                    await reply.clear_reactions()

                await msg.clear_reactions()

            finally:
                self._recent_joins.clear()
                self.massjoin_active = False

    @commands.command()
    @commands.has_role(conf.staff_role)
    async def toggle_massjoin_detection(self, ctx):
        self.massjoin_detect = not self.massjoin_detect
        if self.massjoin_detect:
            await ctx.send("Massjoin detection is now on")
        else:
            await ctx.send("Massjoin detection is now off")

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        channel = message.channel

        if channel not in self._deleted:
            self._deleted[channel] = [message]
            return

        self._deleted[channel].append(message)
        self._deleted[channel] = self._deleted[channel][-conf.max_del_msgs:]

    async def _update_rules(self):
        channel = self.bot.get_channel(conf.rules_channel)
        messages = await channel.history(limit=1000000, oldest_first=True).flatten()
        self._rules = {}

        for message in messages:
            content = message.clean_content
            matches = re.finditer(r"(\d+) - (.+?)(?=[\n ]+\d+? - |$)", content, flags=re.DOTALL)

            for rule in matches:
                if rule[0] == "":
                    continue

                number = rule[1]
                text = rule[2]

                if self._rules.get(number) is None:
                    self._rules[number] = text

    @commands.command(hidden=True)
    @commands.has_role(conf.staff_role)
    async def update_rules(self, ctx):
        await self._update_rules()
        await ctx.send("The rules were updated successully")

def setup(bot):
    bot.add_cog(RulesEnforcer(bot))

