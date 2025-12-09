# bot.py
import os

from keep_alive import keep_alive

keep_alive()

import random
import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands
from discord import app_commands
from discord.utils import get

# ------------- KONFIG -------------
TOKEN = os.getenv("DISCORD_TOKEN"  # <--- Pamiętaj: to jest NAZWA, a nie token!
                  )
PARAGIARNIA_CHANNEL_NAME = "paragiarnia"
TIMEZONE = "Europe/Warsaw"
# ----------------------------------

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = False  # niepotrzebne, używamy interactionów

bot = commands.Bot(command_prefix="!", intents=intents)

# mapowanie przycisk -> (nazwa roli, prefix)
PRODUCTS = {
    "CatLean": ("CatLean", "CL"),
    "Thunderhack": ("Thunderhack", "TH"),
    "Veltragossa": ("Veltragossa", "VG"),
    "Grim Client": ("Grim Client", "GC"),
    "Shoreline": ("Shoreline", "SL"),
    "Custom": ("Custom", "CS"),
}

PAYMENT_METHODS = ["blik", "psc", "my psc", "anarchia"]


def gen_mid_digits(n=10):
    return "".join(random.choice("0123456789") for _ in range(n))


def now_str():
    tz = ZoneInfo(TIMEZONE)
    return datetime.datetime.now(tz=tz).strftime("%Y-%m-%d %H:%M:%S %Z")


async def ensure_paragiarnia_channel(
        guild: discord.Guild) -> discord.TextChannel:
    ch = get(guild.text_channels, name=PARAGIARNIA_CHANNEL_NAME)
    if ch:
        return ch
    # tworzymy prosty kanał tekstowy (możesz później dopracować permisiony)
    overwrites = {
        guild.default_role:
        discord.PermissionOverwrite(read_messages=False),
        guild.me:
        discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }
    ch = await guild.create_text_channel(PARAGIARNIA_CHANNEL_NAME,
                                         overwrites=overwrites,
                                         reason="Kanał do paragonów dla bota")
    return ch


class PaymentView(discord.ui.View):

    def __init__(self, product_name: str, purchaser: discord.Member,
                 target_member: discord.Member, original_message):
        super().__init__(timeout=None)
        self.product_name = product_name
        self.purchaser = purchaser
        self.target_member = target_member
        self.original_message = original_message  # message, żeby edytować i zablokować przyciski
        # dynamicznie dodamy przyciski w __init__? tu zrobimy statycznie w klasie niżej

    async def do_finalize(self, interaction: discord.Interaction, method: str):
        # przydziel paragon i wyślij log
        guild = interaction.guild
        prefix = PRODUCTS.get(self.product_name, ("Custom", "CS"))[1]
        mid = gen_mid_digits(10)
        method_label = method.replace(" ", "_")
        paragon = f"{prefix}{mid}{method_label}"

        # znajdź kanał paragiarnia (albo utwórz)
        paragiarnia = await ensure_paragiarnia_channel(guild)

        embed = discord.Embed(title="Nowy paragon", color=0x2F3136)
        embed.add_field(name="Paragon", value=paragon, inline=False)
        embed.add_field(
            name="Klient",
            value=f"{self.target_member} ({self.target_member.id})",
            inline=False)
        embed.add_field(name="Produkt", value=self.product_name, inline=True)
        embed.add_field(name="Metoda płatności", value=method, inline=True)
        embed.add_field(name="Kanał (ticket)",
                        value=interaction.channel.mention,
                        inline=False)
        embed.set_footer(text=f"Data: {now_str()}")

        await paragiarnia.send(embed=embed)

        # potwierdzenie w ticket channel (edytujemy oryginalny komunikat, wyłączamy przyciski)
        try:
            # zablokuj/przyciemnij przyciski w oryginalnym message
            if self.original_message:
                view = discord.ui.View()
                # kopiujemy przyciski jako nieaktywne (można też po prostu edytować content)
                for child in self.original_message.components[
                        0].children:  # components -> pierwszy wiersz
                    child.disabled = True
                    view.add_item(child)
                await self.original_message.edit(view=view)
        except Exception:
            pass

        await interaction.response.send_message(
            f"Paragon wygenerowany: `{paragon}` — zalogowano w #{PARAGIARNIA_CHANNEL_NAME}.",
            ephemeral=True)

    # przyciski metod płatności:
    @discord.ui.button(label="blik",
                       style=discord.ButtonStyle.primary,
                       custom_id="pay_blik")
    async def pay_blik(self, interaction: discord.Interaction,
                       button: discord.ui.Button):
        if interaction.user != self.purchaser:
            return await interaction.response.send_message(
                "Tylko inicjator akcji może dokończyć proces.", ephemeral=True)
        await self.do_finalize(interaction, "blik")

    @discord.ui.button(label="psc",
                       style=discord.ButtonStyle.primary,
                       custom_id="pay_psc")
    async def pay_psc(self, interaction: discord.Interaction,
                      button: discord.ui.Button):
        if interaction.user != self.purchaser:
            return await interaction.response.send_message(
                "Tylko inicjator akcji może dokończyć proces.", ephemeral=True)
        await self.do_finalize(interaction, "psc")

    @discord.ui.button(label="my psc",
                       style=discord.ButtonStyle.primary,
                       custom_id="pay_mypsc")
    async def pay_mypsc(self, interaction: discord.Interaction,
                        button: discord.ui.Button):
        if interaction.user != self.purchaser:
            return await interaction.response.send_message(
                "Tylko inicjator akcji może dokończyć proces.", ephemeral=True)
        await self.do_finalize(interaction, "my psc")

    @discord.ui.button(label="anarchia",
                       style=discord.ButtonStyle.danger,
                       custom_id="pay_anarchia")
    async def pay_anarchia(self, interaction: discord.Interaction,
                           button: discord.ui.Button):
        if interaction.user != self.purchaser:
            return await interaction.response.send_message(
                "Tylko inicjator akcji może dokończyć proces.", ephemeral=True)
        await self.do_finalize(interaction, "anarchia")


class ProductView(discord.ui.View):

    def __init__(self, purchaser: discord.Member,
                 target_member: discord.Member):
        super().__init__(timeout=None)
        self.purchaser = purchaser
        self.target_member = target_member
        self.original_message = None  # wypełnimy po wysłaniu

    async def assign_role_and_open_payment(self,
                                           interaction: discord.Interaction,
                                           product_key: str):
        if interaction.user != self.purchaser:
            return await interaction.response.send_message(
                "Tylko inicjator akcji może używać tych przycisków.",
                ephemeral=True)

        guild = interaction.guild
        role_name, prefix = PRODUCTS[product_key]
        # szukamy roli, jeśli nie ma — tworzymy ją
        role = get(guild.roles, name=role_name)
        if role is None:
            try:
                role = await guild.create_role(
                    name=role_name, reason="Tworzona przez bota - produkt")
            except Exception as e:
                await interaction.response.send_message(
                    f"Nie mogę utworzyć roli: {e}", ephemeral=True)
                return

        # nadaj rolę targetowi
        try:
            await self.target_member.add_roles(role,
                                               reason=f"Zakup: {product_key}")
        except Exception as e:
            await interaction.response.send_message(
                f"Nie mogę nadać roli temu użytkownikowi: {e}", ephemeral=True)
            return

        # pokaż view z metodami płatności
        payment_view = PaymentView(product_name=product_key,
                                   purchaser=self.purchaser,
                                   target_member=self.target_member,
                                   original_message=self.original_message)
        # wyślij nowy embed z wyborem płatności edytując oryginalny komunikat (możesz też wysłać nowy)
        embed = discord.Embed(
            title="Wybierz metodę płatności",
            description=
            f"Produkt: **{product_key}**\nNadałem rolę `{role_name}` użytkownikowi {self.target_member.mention}. Wybierz metodę płatności.",
            color=0x00AAFF)
        await interaction.response.send_message(embed=embed,
                                                view=payment_view,
                                                ephemeral=True)

        # opcjonalnie log w kanale ticket że przydzielono role
        try:
            await interaction.followup.send(
                f"Nadano rolę `{role_name}` użytkownikowi {self.target_member.mention}. Wybierz metodę płatności (ephemeral).",
                ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(label="Anuluj",
                       style=discord.ButtonStyle.secondary,
                       custom_id="prod_cancel")
    async def cancel(self, interaction: discord.Interaction,
                     button: discord.ui.Button):
        if interaction.user != self.purchaser:
            return await interaction.response.send_message(
                "Tylko inicjator akcji może anulować.", ephemeral=True)
        # zdeaktywuj view
        for child in self.children:
            child.disabled = True
        try:
            if self.original_message:
                await self.original_message.edit(content="Zadanie anulowane.",
                                                 view=self)
            await interaction.response.send_message("Anulowano.",
                                                    ephemeral=True)
        except Exception:
            await interaction.response.send_message("Anulowano.",
                                                    ephemeral=True)

    @discord.ui.button(label="CatLean",
                       style=discord.ButtonStyle.primary,
                       custom_id="prod_catlean")
    async def catlean(self, interaction: discord.Interaction,
                      button: discord.ui.Button):
        await self.assign_role_and_open_payment(interaction, "CatLean")

    @discord.ui.button(label="Thunderhack",
                       style=discord.ButtonStyle.primary,
                       custom_id="prod_thunderhack")
    async def thunderhack(self, interaction: discord.Interaction,
                          button: discord.ui.Button):
        await self.assign_role_and_open_payment(interaction, "Thunderhack")

    @discord.ui.button(label="Veltragossa",
                       style=discord.ButtonStyle.primary,
                       custom_id="prod_veltragossa")
    async def veltragossa(self, interaction: discord.Interaction,
                          button: discord.ui.Button):
        await self.assign_role_and_open_payment(interaction, "Veltragossa")

    @discord.ui.button(label="Grim Client",
                       style=discord.ButtonStyle.primary,
                       custom_id="prod_grimclient")
    async def grimclient(self, interaction: discord.Interaction,
                         button: discord.ui.Button):
        await self.assign_role_and_open_payment(interaction, "Grim Client")

    @discord.ui.button(label="Shoreline",
                       style=discord.ButtonStyle.primary,
                       custom_id="prod_shoreline")
    async def shoreline(self, interaction: discord.Interaction,
                        button: discord.ui.Button):
        await self.assign_role_and_open_payment(interaction, "Shoreline")

    @discord.ui.button(label="Custom",
                       style=discord.ButtonStyle.primary,
                       custom_id="prod_custom")
    async def custom(self, interaction: discord.Interaction,
                     button: discord.ui.Button):
        await self.assign_role_and_open_payment(interaction, "Custom")


@bot.event
async def on_ready():
    print(f"Zalogowano jako {bot.user} (id: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Zsynchronizowano {len(synced)} komend drzewa.")
    except Exception as e:
        print("Błąd podczas sync:", e)


# Slash command: /zakup_udany @user
@bot.tree.command(
    name="zakup_udany",
    description=
    "Oznacz zakup jako udany i wygeneruj panel (używaj w kanale ticket-xxx).")
@app_commands.describe(
    member="Użytkownik, którego dotyczy zakup (np. klient w tickecie)")
async def zakup_udany(interaction: discord.Interaction,
                      member: discord.Member):
    # sprawdź czy kanał to ticket-xxxx
    channel = interaction.channel
    if channel is None or not getattr(channel, "name",
                                      "").lower().startswith("ticket-"):
        await interaction.response.send_message(
            "Tę komendę możesz użyć tylko w kanale ticket-xxxx.",
            ephemeral=True)
        return

    purchaser = interaction.user  # inicjator akcji — tylko on może zatwierdzać dalej
    target_member = member

    embed = discord.Embed(
        title="Panel sprzedaży — wybierz produkt",
        description=
        f"Klient: {target_member.mention}\nWybierz przycisk odpowiadający zakupionemu produktowi.\nAnuluj — porzuć operację.",
        color=0x00FF99)
    view = ProductView(purchaser=purchaser, target_member=target_member)
    # wyślij wiadomość z przyciskami
    await interaction.response.send_message(embed=embed, view=view)
    # zapisz referencję do oryginalnej wiadomości (żeby później dezaktywować/edytować)
    sent = await interaction.original_response()
    view.original_message = sent


if __name__ == "__main__":
    if TOKEN is None:
        print("Proszę ustawić zmienną środowiskową DISCORD_TOKEN")
    else:
        bot.run(TOKEN)
