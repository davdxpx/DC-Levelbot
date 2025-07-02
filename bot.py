import discord
from discord import app_commands, ForumChannel, TextStyle, Embed
from discord.ui import Button, View, Modal, TextInput
import os
from dotenv import load_dotenv
import datetime

# Lade Umgebungsvariablen aus der .env Datei
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPEN_TICKET_CHANNEL_ID = int(os.getenv("OPEN_TICKET_CHANNEL_ID"))
APPEALS_FORUM_ID = int(os.getenv("APPEALS_FORUM_ID"))
ADMIN_MOD_ROLE_ID = os.getenv("ADMIN_MOD_ROLE_ID")
TICKET_LOG_CHANNEL_ID = os.getenv("TICKET_LOG_CHANNEL_ID")
# Optional: Rollen-ID, die Threads schließen darf (zusätzlich zu Admins/Moderatoren mit Kanalrechten)
TICKET_CLOSER_ROLE_ID = os.getenv("TICKET_CLOSER_ROLE_ID")


# Intents für den Bot definieren
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True # Wichtig für User-Info und DM

# Client-Instanz erstellen
class TicketBotClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.add_view(TicketPanelView(client=self))
        self.add_view(TicketActionsView(client=self)) # Enthält jetzt auch Close
        # self.add_view(CloseTicketModal()) # Modals müssen nicht persistent gemacht werden
        await self.tree.sync()
        print("Slash-Befehle synchronisiert.")

client = TicketBotClient(intents=intents)

# --- Modal für den Schließungsgrund ---
class CloseTicketModal(Modal, title="Ticket schließen"):
    reason_input = TextInput(
        label="Grund für die Schließung (optional)",
        style=TextStyle.paragraph,
        required=False,
        placeholder="Gib hier einen optionalen Grund für den Benutzer an."
    )

    def __init__(self, ticket_actions_view: 'TicketActionsView', original_interaction: discord.Interaction):
        super().__init__(timeout=None)
        self.ticket_actions_view = ticket_actions_view
        self.original_interaction = original_interaction # Die Interaktion, die das Modal geöffnet hat

    async def on_submit(self, interaction: discord.Interaction):
        # Diese Interaktion ist die des Modal-Submit-Buttons
        reason = self.reason_input.value or "Kein Grund angegeben."
        # Die eigentliche Schließlogik wird in der TicketActionsView aufgerufen
        await self.ticket_actions_view.finalize_close_ticket(self.original_interaction, interaction, reason)

# --- View für Aktionen innerhalb eines Ticket-Threads (Claim, Close etc.) ---
class TicketActionsView(View):
    def __init__(self, client: TicketBotClient = None):
        super().__init__(timeout=None)
        self.client_ref = client
        # Dynamisch Buttons hinzufügen, damit wir ihren Status später ändern können
        self.claim_button = Button(label="✅ Claim Ticket", style=discord.ButtonStyle.success, custom_id="ticket_claim")
        self.claim_button.callback = self.claim_button_callback
        self.add_item(self.claim_button)

        self.close_button = Button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="ticket_close")
        self.close_button.callback = self.close_button_callback
        self.add_item(self.close_button)


    async def _check_permissions(self, interaction: discord.Interaction) -> bool:
        """Überprüft, ob der Benutzer die Berechtigung hat, die Aktion auszuführen."""
        # Admins dürfen immer
        if interaction.user.guild_permissions.administrator:
            return True

        # Überprüfe auf TICKET_CLOSER_ROLE_ID (oder Mod/Admin Rollen)
        # Dies ist eine vereinfachte Prüfung. Ideal wäre eine Konfiguration von erlaubten Rollen.
        if TICKET_CLOSER_ROLE_ID:
            closer_role = interaction.guild.get_role(int(TICKET_CLOSER_ROLE_ID))
            if closer_role and closer_role in interaction.user.roles:
                return True

        # Fallback: Hat der User "Manage Threads" in diesem Kanal? (Nicht perfekt, da Forum)
        # Besser wäre es, spezifische Rollen-IDs für Moderatoren zu haben.
        if interaction.channel.permissions_for(interaction.user).manage_threads:
             return True

        await interaction.response.send_message("Du hast nicht die erforderlichen Berechtigungen, um diese Aktion auszuführen.", ephemeral=True)
        return False

    async def claim_button_callback(self, interaction: discord.Interaction, button: Button):
        if not await self._check_permissions(interaction): return
        if not self.client_ref: self.client_ref = interaction.client

        original_message = interaction.message
        embed = original_message.embeds[0] if original_message.embeds else discord.Embed()

        # Prüfen, ob schon geclaimed (z.B. durch Button-Label oder Embed-Text)
        if button.label == "Geclaimed" or "Geclaimed von:" in embed.description or any("Geclaimed von:" in field.name for field in embed.fields):
            await interaction.response.send_message("Dieses Ticket wurde bereits geclaimed.", ephemeral=True)
            return

        claimer = interaction.user
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        new_description_part = f"\n\n**✅ Geclaimed von:** {claimer.mention} am {timestamp}"
        if embed.description:
            embed.description += new_description_part
        else:
            embed.description = new_description_part

        button.disabled = True
        button.label = "Geclaimed"
        button.style = discord.ButtonStyle.secondary

        await original_message.edit(embed=embed, view=self)
        await interaction.response.send_message(f"Du hast dieses Ticket geclaimed.", ephemeral=True)

        ticket_creator_field = next((field for field in embed.fields if field.name == "Ersteller"), None)
        creator_mention = ticket_creator_field.value if ticket_creator_field else "dem Ersteller"

        await self.log_ticket_action(interaction, "Ticket Geclaimed", f"Ticket von {creator_mention} wurde von {claimer.mention} geclaimed.", discord.Color.green())

    async def close_button_callback(self, interaction: discord.Interaction, button: Button):
        if not await self._check_permissions(interaction): return
        if not self.client_ref: self.client_ref = interaction.client

        # Modal für den Schließungsgrund anzeigen
        # Die Interaktion vom Button-Klick wird an das Modal weitergegeben
        modal = CloseTicketModal(ticket_actions_view=self, original_interaction=interaction)
        await interaction.response.send_modal(modal)
        # Die weitere Logik (finalize_close_ticket) wird nach dem Absenden des Modals ausgeführt.

    async def finalize_close_ticket(self, original_button_interaction: discord.Interaction, modal_submit_interaction: discord.Interaction, reason: str):
        """Wird nach dem Absenden des CloseTicketModal aufgerufen."""
        # original_button_interaction ist die Interaktion vom Klick auf "Close Ticket"
        # modal_submit_interaction ist die Interaktion vom Absenden des Modals

        closer = modal_submit_interaction.user # Der User, der das Modal abgeschickt hat
        thread = original_button_interaction.channel
        original_message = original_button_interaction.message # Die Nachricht mit den Buttons

        if not isinstance(thread, discord.Thread):
            await modal_submit_interaction.response.send_message("Fehler: Dies ist kein Thread-Kanal.", ephemeral=True)
            return

        # Buttons deaktivieren
        self.claim_button.disabled = True
        if self.claim_button.label != "Geclaimed": # Falls es noch nicht geclaimed war
            self.claim_button.label = "Aktion nicht mehr verfügbar"
            self.claim_button.style = discord.ButtonStyle.secondary
        self.close_button.disabled = True
        self.close_button.label = "Geschlossen"
        self.close_button.style = discord.ButtonStyle.secondary

        await original_message.edit(view=self) # Buttons auf der ursprünglichen Nachricht aktualisieren

        # Embed für die Schließungsnachricht im Thread
        close_embed = Embed(
            title="🔒 Ticket Geschlossen",
            description=f"Dieses Ticket wurde von {closer.mention} geschlossen.",
            color=discord.Color.dark_grey(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        close_embed.add_field(name="Grund", value=reason, inline=False)

        # Original-Embed der Ticket-Info holen, um den Ersteller zu finden
        ticket_embed = original_message.embeds[0] if original_message.embeds else None
        ticket_creator_user = None
        if ticket_embed:
            creator_field = next((field for field in ticket_embed.fields if field.name == "Ersteller"), None)
            if creator_field:
                try:
                    # Extrahiere User ID aus Mention, z.B. <@123456789012345678> (oder <@!ID>)
                    user_id_str = creator_field.value.split('<@')[-1].split('>')[0].replace('!', '')
                    user_id = int(user_id_str)
                    ticket_creator_user = self.client_ref.get_user(user_id) or await self.client_ref.fetch_user(user_id)
                except Exception as e:
                    print(f"Konnte Ticket-Ersteller nicht aus Embed extrahieren: {e} (Field Value: {creator_field.value})")


        try:
            await thread.send(embed=close_embed)

            # Thread umbenennen und archivieren/sperren
            new_name = f"[Geschlossen] {thread.name}".replace("[Offen]", "").replace("[Geclaimed]", "").strip()
            if len(new_name) > 100: new_name = new_name[:97] + "..."

            await thread.edit(name=new_name, archived=True, locked=True)
            # Bestätigung an den Admin/Mod, der geschlossen hat (über die Modal-Interaktion)
            await modal_submit_interaction.response.send_message(f"Ticket erfolgreich geschlossen und archiviert. Grund: {reason}", ephemeral=True)

            # Log-Nachricht
            log_message = f"Ticket {thread.mention} wurde von {closer.mention} geschlossen.\nGrund: {reason}"
            await self.log_ticket_action(modal_submit_interaction, "Ticket Geschlossen", log_message, discord.Color.red())

            # DM an den Ticketersteller (falls gefunden)
            if ticket_creator_user:
                try:
                    dm_embed = Embed(
                        title="Dein Ticket wurde geschlossen",
                        description=f"Hallo {ticket_creator_user.name},\n\nDein Ticket \"{thread.name.replace('[Geschlossen]', '').strip()}\" wurde von einem Teammitglied geschlossen.",
                        color=discord.Color.blue()
                    )
                    dm_embed.add_field(name="Grund der Schließung", value=reason, inline=False)
                    dm_embed.set_footer(text=f"Server: {original_button_interaction.guild.name}")
                    await ticket_creator_user.send(embed=dm_embed)
                except discord.Forbidden:
                    print(f"Konnte keine DM an {ticket_creator_user.name} senden (DMs möglicherweise deaktiviert).")
                except Exception as e:
                    print(f"Fehler beim Senden der DM an den Ticketersteller: {e}")

        except discord.Forbidden:
            await modal_submit_interaction.response.send_message("Fehler: Ich habe keine Berechtigungen, um den Thread zu bearbeiten oder Nachrichten zu senden.", ephemeral=True)
        except Exception as e:
            await modal_submit_interaction.response.send_message(f"Ein unerwarteter Fehler ist aufgetreten: {e}", ephemeral=True)
            print(f"Fehler beim Schließen des Tickets: {e}")


    async def log_ticket_action(self, interaction: discord.Interaction, action_name: str, message: str, color: discord.Color):
        if not TICKET_LOG_CHANNEL_ID: return
        client_to_use = self.client_ref if self.client_ref else interaction.client
        if not client_to_use: return

        log_channel_id = 0
        try:
            log_channel_id = int(TICKET_LOG_CHANNEL_ID)
        except ValueError:
            print(f"FEHLER: TICKET_LOG_CHANNEL_ID ('{TICKET_LOG_CHANNEL_ID}') ist keine gültige ID.")
            return

        log_channel = client_to_use.get_channel(log_channel_id)
        if log_channel and isinstance(log_channel, discord.TextChannel):
            embed = Embed(title=f"Ticket System: {action_name}", description=message, color=color)
            embed.set_footer(text=f"Aktion durchgeführt von: {interaction.user.name} ({interaction.user.id})")
            embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
            if isinstance(interaction.channel, discord.Thread): # Gilt für Claim/Close
                 embed.add_field(name="Betroffener Ticket Thread", value=interaction.channel.mention, inline=False)

            try:
                await log_channel.send(embed=embed)
            except Exception as e:
                print(f"Fehler beim Senden der Log-Nachricht: {e}")
        else:
            print(f"Log-Kanal mit ID {TICKET_LOG_CHANNEL_ID} nicht gefunden oder kein Textkanal.")


# --- Ticket Panel View mit Buttons und Logik --- (Bleibt größtenteils gleich)
class TicketPanelView(View):
    def __init__(self, client: TicketBotClient = None):
        super().__init__(timeout=None)
        self.client_ref = client

        button_actions = [
            ("❓ General Help", "ticket_general_help", discord.ButtonStyle.primary),
            ("🐛 Bug Report", "ticket_bug_report", discord.ButtonStyle.danger),
            ("👤 User Report", "ticket_user_report", discord.ButtonStyle.secondary),
            ("💡 Other Issue", "ticket_other_issue", discord.ButtonStyle.success),
        ]
        for label, custom_id, style in button_actions:
            button = Button(label=label, style=style, custom_id=custom_id)
            # Wichtig: Das Label vom Button wird jetzt als Ticket-Typ Name verwendet
            button.callback = lambda i, b=button: self.create_ticket_callback(i, b.label) # Label übergeben
            self.add_item(button)

    async def create_ticket_callback(self, interaction: discord.Interaction, ticket_type_name: str):
        if not self.client_ref: self.client_ref = interaction.client
        # ... (Rest der create_ticket_callback Methode bleibt sehr ähnlich)
        user = interaction.user
        appeals_forum: ForumChannel = self.client_ref.get_channel(APPEALS_FORUM_ID)
        if not appeals_forum or not isinstance(appeals_forum, discord.ForumChannel):
            await interaction.response.send_message("Fehler: Das 'Appeals'-Forum ist nicht korrekt konfiguriert.", ephemeral=True)
            return

        thread_title = f"[Offen] {ticket_type_name} - {user.name}"
        if len(thread_title) > 100: thread_title = thread_title[:97] + "..."

        now = datetime.datetime.now(datetime.timezone.utc)
        timestamp_formatted = now.strftime("%Y-%m-%d %H:%M:%S UTC")

        ticket_embed = Embed(
            title=f"🎫 Neues Ticket: {ticket_type_name}",
            description=f"Ein neues Ticket wurde erstellt und wartet auf Bearbeitung.",
            color=discord.Color.orange()
        )
        ticket_embed.add_field(name="Ersteller", value=f"{user.mention} ({user.id})", inline=False)
        ticket_embed.add_field(name="Ticket Typ", value=ticket_type_name, inline=False)
        ticket_embed.add_field(name="Erstellt am", value=timestamp_formatted, inline=False)

        initial_content_for_thread_creation = f"Neues Ticket von {user.mention}."

        mention_text = ""
        if ADMIN_MOD_ROLE_ID:
            try:
                role = interaction.guild.get_role(int(ADMIN_MOD_ROLE_ID))
                if role: mention_text = f"\n{role.mention}, ein neues Ticket benötigt Aufmerksamkeit!"
            except: pass

        try:
            thread_message_content = initial_content_for_thread_creation + mention_text
            # Manchmal ist es besser, die erste Nachricht leer zu lassen, wenn man direkt ein Embed sendet
            # thread_message_content = discord.utils.MISSING # Sendet keine Startnachricht, nur das Embed unten

            # Versuche, den passenden Tag zu finden
            applied_tags = []
            target_tag_name = ticket_type_name # z.B. "General Help"
            available_tags = appeals_forum.available_tags

            found_tag = discord.utils.find(lambda tag: tag.name == target_tag_name, available_tags)
            if found_tag:
                applied_tags.append(found_tag)
                print(f"INFO: Forum-Tag '{target_tag_name}' gefunden und wird angewendet.")
            else:
                print(f"WARNUNG: Forum-Tag '{target_tag_name}' nicht im Forum '{appeals_forum.name}' (ID: {APPEALS_FORUM_ID}) gefunden. Stelle sicher, dass Tags exakt so heißen wie die Ticket-Typen (Button-Labels).")

            thread = await appeals_forum.create_thread(
                name=thread_title,
                content=thread_message_content,
                applied_tags=applied_tags if applied_tags else discord.utils.MISSING
            )
            ticket_embed.set_footer(text=f"Ticket ID: {thread.id}")

            await thread.send(embed=ticket_embed, view=TicketActionsView(client=self.client_ref))

            tag_info_msg = f" (Tag: {found_tag.name})" if found_tag else " (Hinweis: Kein passender Forum-Tag für diesen Ticket-Typ gefunden.)"
            await interaction.response.send_message(
                f"Dein Ticket '{ticket_type_name}' wurde erfolgreich erstellt! Du findest es hier: {thread.mention}{tag_info_msg}",
                ephemeral=True
            )

            # Log action
            log_helper_view = TicketActionsView(client=self.client_ref) # Brauchen eine Instanz für log_ticket_action
            log_message_detail = f"Neues Ticket '{ticket_type_name}' von {user.mention} erstellt im Thread {thread.mention}."
            if found_tag:
                log_message_detail += f" Tag '{found_tag.name}' angewendet."
            else:
                log_message_detail += " Kein passender Forum-Tag gefunden/angewendet."
            await log_helper_view.log_ticket_action(interaction, "Ticket Erstellt", log_message_detail, discord.Color.blue())

        except discord.Forbidden as fe:
            await interaction.response.send_message(f"Fehler beim Erstellen des Tickets: Ich habe möglicherweise nicht die Berechtigung, Threads zu erstellen oder Tags anzuwenden. Bitte überprüfe meine Rollenberechtigungen im Forum. ({fe})", ephemeral=True)
            print(f"FEHLER (Forbidden) beim Erstellen des Tickets oder Anwenden von Tags: {fe}")
        except Exception as e:
            await interaction.response.send_message(f"Fehler beim Erstellen des Tickets: {e}",ephemeral=True)
            print(f"FEHLER beim Erstellen des Tickets: {e}")


# --- Event: Bot ist bereit --- (Bleibt größtenteils gleich)
@client.event
async def on_ready():
    print(f'{client.user} ist jetzt online und bereit!')
    print(f'User ID: {client.user.id}')
    print(f'Open a Ticket Channel ID: {OPEN_TICKET_CHANNEL_ID}')
    print(f'Appeals Forum ID: {APPEALS_FORUM_ID}')
    if ADMIN_MOD_ROLE_ID: print(f'Admin/Mod Role ID: {ADMIN_MOD_ROLE_ID}')
    if TICKET_LOG_CHANNEL_ID: print(f'Ticket Log Channel ID: {TICKET_LOG_CHANNEL_ID}')
    if TICKET_CLOSER_ROLE_ID: print(f'Ticket Closer Role ID: {TICKET_CLOSER_ROLE_ID}')
    print('------')
    # Kanalüberprüfungen... (wie gehabt)

# --- Slash-Befehl: Setup Ticket Panel --- (Bleibt größtenteils gleich)
@client.tree.command(name="setup_ticket_panel", description="Postet das Ticket-Panel im 'Open a Ticket'-Kanal.")
@app_commands.checks.has_permissions(administrator=True)
async def setup_ticket_panel_command(interaction: discord.Interaction):
    # ... (wie gehabt)
    channel = client.get_channel(OPEN_TICKET_CHANNEL_ID)
    if not channel or not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(f"Fehler: Kanal (ID: {OPEN_TICKET_CHANNEL_ID}) nicht gefunden/Textkanal.", ephemeral=True)
        return

    embed = Embed(
        title="🎫 Ticket Support",
        description="Wähle die Kategorie deines Anliegens, um ein Ticket zu erstellen.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Ein Teammitglied wird sich bald kümmern.")
    try:
        await channel.send(embed=embed, view=TicketPanelView(client=client)) # Client übergeben
        await interaction.response.send_message(f"Ticket-Panel in {channel.mention} gepostet.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Fehler beim Posten des Panels: {e}", ephemeral=True)

@setup_ticket_panel_command.error
async def setup_ticket_panel_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # ... (wie gehabt)
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Keine Admin-Berechtigungen.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Fehler: {error}", ephemeral=True)


if __name__ == "__main__":
    if DISCORD_TOKEN:
        client.run(DISCORD_TOKEN)
    else:
        print("FEHLER: DISCORD_TOKEN nicht in .env gefunden.")
