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

import json

# Globale Variable für geladene Ticket-Kategorien
TICKET_CATEGORIES = []

def load_ticket_categories():
    """Lädt Ticket-Kategorien aus ticket_categories.json."""
    global TICKET_CATEGORIES
    try:
        with open("ticket_categories.json", "r", encoding="utf-8") as f:
            categories = json.load(f)
        # Grundlegende Validierung (kann erweitert werden)
        if not isinstance(categories, list):
            print("FEHLER: ticket_categories.json ist keine Liste.")
            TICKET_CATEGORIES = []
            return False
        for cat in categories:
            if not all(k in cat for k in ["category_id", "button_label", "button_custom_id", "button_style", "forum_tag_name", "modal_title", "modal_custom_id_prefix", "modal_questions"]):
                print(f"FEHLER: Kategorie {cat.get('category_id', 'Unbekannt')} in ticket_categories.json fehlen notwendige Schlüssel.")
                TICKET_CATEGORIES = [] # Bei Fehler keine Kategorien laden, um inkonsistenten Zustand zu vermeiden
                return False
            if not isinstance(cat["modal_questions"], list):
                print(f"FEHLER: 'modal_questions' in Kategorie {cat['category_id']} ist keine Liste.")
                TICKET_CATEGORIES = []
                return False
            for q_idx, q in enumerate(cat["modal_questions"]):
                 if not all(k_q in q for k_q in ["id", "label", "style", "required"]):
                    print(f"FEHLER: Frage {q_idx} in Kategorie {cat['category_id']} fehlen notwendige Schlüssel (id, label, style, required).")
                    TICKET_CATEGORIES = []
                    return False
        TICKET_CATEGORIES = categories
        print(f"{len(TICKET_CATEGORIES)} Ticket-Kategorien erfolgreich aus ticket_categories.json geladen.")
        return True
    except FileNotFoundError:
        print("WARNUNG: ticket_categories.json nicht gefunden. Das Ticket-Panel wird keine Optionen anzeigen.")
        TICKET_CATEGORIES = []
        return False # Datei nicht gefunden, aber kein harter Fehler für den Bot-Start unbedingt
    except json.JSONDecodeError as e:
        print(f"FEHLER: ticket_categories.json ist nicht valides JSON: {e}")
        TICKET_CATEGORIES = []
        return False
    except Exception as e:
        print(f"FEHLER: Unerwarteter Fehler beim Laden von ticket_categories.json: {e}")
        TICKET_CATEGORIES = []
        return False

# Client-Instanz erstellen
class TicketBotClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.ticket_categories = [] # Wird in setup_hook geladen

    async def setup_hook(self):
        if load_ticket_categories(): # Lädt in globale Variable TICKET_CATEGORIES
             self.ticket_categories = TICKET_CATEGORIES # Kopiere in die Client-Instanz
        else:
             # Hier könnte man entscheiden, ob der Bot ohne Kategorien überhaupt starten soll
             print("Bot startet ohne geladene Ticket-Kategorien aufgrund von Fehlern.")
             self.ticket_categories = []


        # Views müssen die Kategorien oder den Client bekommen, um darauf zuzugreifen
        # TicketPanelView wird die Kategorien direkt verwenden
        self.add_view(TicketPanelView(client=self, categories=self.ticket_categories))
        self.add_view(TicketActionsView(client=self)) # Enthält jetzt auch Close

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

        # Aktualisiere das Embed, um den Claim-Status anzuzeigen
        # Entferne alte Claim-Felder, falls vorhanden (defensive Programmierung)
        embed.fields = [field for field in embed.fields if field.name != "✅ Geclaimed von"]
        
        embed.add_field(name="✅ Geclaimed von", value=f"{claimer.mention}\nam {timestamp}", inline=False)
        embed.color = discord.Color.green() # Ändere die Farbe des Embeds zu grün

        # Button-Status anpassen
        button.disabled = True
        button.label = "Geclaimed"
        button.style = discord.ButtonStyle.secondary

        try:
            await original_message.edit(embed=embed, view=self)
            # Nur antworten, wenn die Interaktion noch nicht beantwortet wurde (z.B. durch einen vorherigen Fehler)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Du hast dieses Ticket geclaimed.", ephemeral=True)
        except discord.HTTPException as e:
            print(f"FEHLER: Konnte die Originalnachricht beim Claimen nicht bearbeiten: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Das Ticket wurde als geclaimed markiert, aber die Ursprungsnachricht konnte nicht vollständig aktualisiert werden. Bitte überprüfe den Thread.", ephemeral=True)
            # Dennoch versuchen zu loggen, da der Claim-Vorgang logisch stattgefunden hat
        except Exception as e:
            print(f"FEHLER: Unerwarteter Fehler beim Bearbeiten der Nachricht/Antworten für Claim: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Ein unerwarteter Fehler ist beim Claimen aufgetreten.", ephemeral=True)
            # Dennoch versuchen zu loggen
        
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
        
        # Original-Embed der Ticket-Info aktualisieren
        if original_message.embeds:
            original_ticket_embed = original_message.embeds[0]
            original_ticket_embed.color = discord.Color.dark_grey() # Farbe für geschlossenen Status

            # Entferne das "Geclaimed von"-Feld, da "Geschlossen" der definitive Status ist
            original_ticket_embed.fields = [field for field in original_ticket_embed.fields if field.name != "✅ Geclaimed von"]

            # Füge ein Statusfeld hinzu oder aktualisiere es
            status_field_found = False
            for i, field in enumerate(original_ticket_embed.fields):
                if field.name == "Status":
                    original_ticket_embed.set_field_at(i, name="Status", value=f"🔒 Geschlossen von {closer.mention}", inline=False)
                    status_field_found = True
                    break
            if not status_field_found:
                original_ticket_embed.add_field(name="Status", value=f"🔒 Geschlossen von {closer.mention}", inline=False)

            await original_message.edit(embed=original_ticket_embed, view=self)
        else:
            # Sollte nicht passieren, da wir immer mit einem Embed starten
            await original_message.edit(view=self)

        # Embed für die separate Schließungsnachricht im Thread
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


    async def log_ticket_action(self, interaction: discord.Interaction, action_name: str, message: str, color: discord.Color, thread_id: int = None):
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

            current_thread_id = None
            thread_mention_value = "N/A"

            if isinstance(interaction.channel, discord.Thread): # Für Aktionen innerhalb eines Threads (Claim, Close)
                current_thread_id = interaction.channel.id
                thread_mention_value = interaction.channel.mention
            elif thread_id: # Für Aktionen wie Ticketerstellung
                current_thread_id = thread_id
                # Versuche, den Thread zu fetchen, um einen korrekten Mention zu bekommen, falls möglich
                # Dies ist optional und dient der schöneren Darstellung.
                try:
                    fetched_thread = await client_to_use.fetch_channel(thread_id)
                    if isinstance(fetched_thread, discord.Thread):
                        thread_mention_value = fetched_thread.mention
                    else: # Fallback, falls fetch_channel keinen Thread liefert oder fehlschlägt
                        thread_mention_value = f"<#{thread_id}> (Thread)"
                except (discord.NotFound, discord.Forbidden): # Thread nicht gefunden oder keine Rechte
                    thread_mention_value = f"<#{thread_id}> (Thread)"
                except Exception as e: # Andere Fehler beim Fetchen
                    print(f"Log: Konnte Thread {thread_id} nicht fetchen für Mention: {e}")
                    thread_mention_value = f"<#{thread_id}> (Thread)"

            if current_thread_id:
                embed.add_field(name="Ticket Thread", value=thread_mention_value, inline=True)
                embed.add_field(name="Ticket ID", value=str(current_thread_id), inline=True)
            
            try:
                await log_channel.send(embed=embed)
            except Exception as e:
                print(f"Fehler beim Senden der Log-Nachricht: {e}")
        else:
            print(f"Log-Kanal mit ID {TICKET_LOG_CHANNEL_ID} nicht gefunden oder kein Textkanal.")


# --- Ticket Panel View mit Buttons und Logik ---
class TicketPanelView(View):
    def __init__(self, client: TicketBotClient, categories: list):
        super().__init__(timeout=None)
        self.client_ref = client
        self.categories_data = categories # Speichere die Kategorien-Daten

        if not self.categories_data:
            print("WARNUNG: TicketPanelView wurde ohne Kategorien initialisiert. Es werden keine Buttons angezeigt.")
            # Optional: Einen Hinweis-Button hinzufügen oder nichts tun
            # error_button = Button(label="Fehler: Keine Ticket-Kategorien konfiguriert.", style=discord.ButtonStyle.danger, disabled=True, custom_id="cat_error")
            # self.add_item(error_button)
            return

        for category in self.categories_data:
            button_label = category.get("button_label", "N/A")
            button_emoji = category.get("button_emoji")
            if button_emoji:
                button_label = f"{button_emoji} {button_label}"

            style_str = category.get("button_style", "secondary").lower()
            button_style = getattr(discord.ButtonStyle, style_str, discord.ButtonStyle.secondary)

            # Die custom_id des Buttons ist nun die category_id aus der JSON, um sie eindeutig zu identifizieren
            button = Button(
                label=button_label,
                style=button_style,
                custom_id=category["button_custom_id"] # Verwende die definierte custom_id
            )
            # Wir binden die category_id an den Callback, um zu wissen, welche Kategorie geklickt wurde
            button.callback = lambda i, cat_id=category["category_id"]: self.category_button_callback(i, cat_id)
            self.add_item(button)

    async def category_button_callback(self, interaction: discord.Interaction, category_id: str):
        """Wird aufgerufen, wenn ein Kategorie-Button geklickt wird. Zeigt das Modal an."""
        if not self.client_ref: self.client_ref = interaction.client # Fallback

        # Finde die geklickte Kategorie in den geladenen Daten
        selected_category = next((cat for cat in self.categories_data if cat["category_id"] == category_id), None)

        if not selected_category:
            await interaction.response.send_message("Fehler: Die ausgewählte Ticket-Kategorie konnte nicht gefunden werden. Bitte kontaktiere einen Admin.", ephemeral=True)
            print(f"FEHLER: Kategorie mit ID '{category_id}' nicht in self.categories_data gefunden.")
            return

        # Hier wird das Modal erstellt und angezeigt (nächster Schritt)
        # Erstelle und zeige das Modal dynamisch
        ticket_modal = self.build_ticket_modal(selected_category, self.create_ticket_thread_after_modal)
        await interaction.response.send_modal(ticket_modal)
        # Die weitere Verarbeitung geschieht im on_submit des Modals, welches dann create_ticket_thread_after_modal aufruft.

    def build_ticket_modal(self, category_config: dict, on_submit_callback: callable) -> Modal:
        """Erstellt dynamisch ein Modal basierend auf der Kategoriekonfiguration."""

        modal_title = category_config.get("modal_title", "Ticket Details")
        # Wichtig: Die Custom ID des Modals muss die category_id beinhalten, um sie im on_submit wiederzufinden
        # und darf nicht zu lang sein (max 100 Zeichen).
        modal_custom_id = f"ticket_modal_{category_config['category_id']}"
        if len(modal_custom_id) > 100:
            modal_custom_id = modal_custom_id[:100]


        # Dynamische Modal-Klasse
        class DynamicTicketModal(Modal, title=modal_title):
            # Speichere die category_id und den Callback für on_submit
            # Diese müssen als Klassenattribute oder im Konstruktor übergeben werden,
            # da sie nicht direkt in on_submit verfügbar sind.
            # Lösung: Binde sie an die Instanz im Konstruktor der äußeren Klasse oder übergebe sie hier.

            # Wir verwenden eine etwas andere Herangehensweise, um die Daten in on_submit zu bekommen:
            # Der Callback (on_submit_callback) wird direkt in on_submit verwendet.
            # Die category_id wird Teil der custom_id des Modals sein und dort extrahiert.

            def __init__(self, category_conf: dict, final_callback: callable):
                super().__init__(title=category_conf.get("modal_title", "Ticket Details"), custom_id=f"ticket_modal_{category_conf['category_id']}"[:100])
                self.final_submit_callback = final_callback # z.B. create_ticket_thread_after_modal
                self.category_config_data = category_conf

                for q_config in category_conf.get("modal_questions", []):
                    text_style = discord.TextStyle.short
                    if q_config.get("style", "short").lower() == "paragraph":
                        text_style = discord.TextStyle.paragraph

                    # TextInput custom_id muss eindeutig sein innerhalb des Modals
                    # Wir verwenden hier die 'id' aus der JSON-Konfiguration der Frage.
                    input_field = TextInput(
                        label=q_config["label"],
                        custom_id=q_config["id"], # Eindeutige ID für dieses Feld
                        style=text_style,
                        placeholder=q_config.get("placeholder"),
                        required=q_config.get("required", False),
                        # min_length, max_length können auch konfiguriert werden
                    )
                    self.add_item(input_field)

            async def on_submit(self, interaction: discord.Interaction):
                # Extrahiere Antworten aus dem Modal
                responses = {}
                for item in self.children:
                    if isinstance(item, TextInput):
                        responses[item.custom_id] = item.value

                # Rufe den finalen Callback auf (create_ticket_thread_after_modal)
                # Die category_id muss hier wieder extrahiert werden, z.B. aus der modal custom_id
                # Die custom_id des Modals ist z.B. "ticket_modal_general_help"
                modal_cat_id = self.custom_id.split("ticket_modal_")[-1]

                # Wichtig: Die Interaktion vom Modal muss zunächst bestätigt werden (defer oder send_message)
                # bevor der langlaufende Thread-Erstellungsprozess beginnt.
                # Da create_ticket_thread_after_modal eine followup.send() verwenden wird,
                # können wir hier mit defer() antworten.
                await interaction.response.defer(ephemeral=True, thinking=True) # Zeigt "Bot denkt nach..."

                await self.final_submit_callback(interaction, modal_cat_id, responses)


        return DynamicTicketModal(category_config, on_submit_callback)


    async def create_ticket_thread_after_modal(self, interaction: discord.Interaction, category_id: str, modal_responses: dict):
        """Erstellt den Ticket-Thread, nachdem das Modal ausgefüllt wurde. Enthält Logik der alten create_ticket_callback."""

        if not self.client_ref: self.client_ref = interaction.client # Fallback

        selected_category = next((cat for cat in self.categories_data if cat["category_id"] == category_id), None)
        if not selected_category:
            await interaction.followup.send("Ein interner Fehler ist aufgetreten (Kategorie nicht mehr gefunden beim Erstellen des Threads). Bitte versuche es erneut oder kontaktiere einen Admin.", ephemeral=True)
            print(f"FEHLER: Kategorie mit ID '{category_id}' nicht in self.categories_data gefunden während create_ticket_thread_after_modal.")
            return

        user = interaction.user
        ticket_type_name = selected_category['button_label'] # Button-Label als Ticket-Typ-Name

        appeals_forum: ForumChannel = self.client_ref.get_channel(APPEALS_FORUM_ID) # type: ignore
        if not appeals_forum or not isinstance(appeals_forum, discord.ForumChannel):
            # Wichtig: followup verwenden, da die Interaktion vom Modal kommt und gedeffert wurde
            await interaction.followup.send("Fehler: Das 'Appeals'-Forum ist nicht korrekt konfiguriert. Bitte informiere einen Admin.", ephemeral=True)
            print(f"FEHLER: Appeals-Forum (ID: {APPEALS_FORUM_ID}) nicht gefunden oder kein Forum-Kanal.")
            return

        thread_title = f"[Offen] {ticket_type_name} - {user.name}"
        if len(thread_title) > 100: thread_title = thread_title[:97] + "..."

        now = datetime.datetime.now(datetime.timezone.utc)
        timestamp_formatted = now.strftime("%Y-%m-%d %H:%M:%S UTC")
        
        ticket_embed = Embed(
            title=f"🎫 Neues Ticket: {ticket_type_name}",
            description=f"Ein neues Ticket wurde von {user.mention} erstellt und wartet auf Bearbeitung.",
            color=discord.Color.orange()
        )
        ticket_embed.add_field(name="Ersteller", value=f"{user.mention} ({user.id})", inline=False)
        ticket_embed.add_field(name="Ticket Typ", value=ticket_type_name, inline=False) # Verwende das Button-Label als Typ
        ticket_embed.add_field(name="Erstellt am", value=timestamp_formatted, inline=False)
        
        # Trennlinie und Titel für Modal-Antworten
        if modal_responses: # Nur hinzufügen, wenn es Antworten gibt
            ticket_embed.add_field(name="─" * 30, value="**Vom Benutzer angegebene Informationen:**", inline=False)
            for question_config in selected_category.get("modal_questions", []):
                question_id = question_config["id"]
                question_label = question_config["label"] # Das Label aus der JSON als Feldname
                response_value = modal_responses.get(question_id)

                if not response_value: # Wenn leer
                    if question_config.get("required", False):
                        response_value = "_FEHLER: Erforderliche Angabe fehlt_" # Sollte nicht passieren bei Modal-Validierung
                    else:
                        response_value = "_N/A (Optional)_"

                # Discord Field Value Limit ist 1024
                ticket_embed.add_field(name=f"{question_label}", value=str(response_value)[:1020], inline=False)
        
        initial_content_for_thread_creation = f"Neues Ticket von {user.mention}."
        mention_text = ""
        # Verwende ADMIN_MOD_ROLE_ID (aus .env, die der Bot als ADMIN_MOD_ROLE_ID kennt)
        # Die .env.example nennt es ADMIN_MOD_PING_ROLE_ID zur Klarstellung des Zwecks
        admin_mod_ping_role_id_str = os.getenv("ADMIN_MOD_PING_ROLE_ID") # Hole es frisch, falls es geändert wurde
        if admin_mod_ping_role_id_str:
            try:
                role_id = int(admin_mod_ping_role_id_str)
                if interaction.guild: # Stelle sicher, dass wir einen Guild-Kontext haben
                    role = interaction.guild.get_role(role_id)
                    if role:
                        mention_text = f"\n{role.mention}, ein neues Ticket benötigt Aufmerksamkeit!"
                    else:
                        print(f"WARNUNG: ADMIN_MOD_PING_ROLE_ID {role_id} nicht auf dem Server gefunden.")
                else: # Sollte nicht passieren bei Guild-basierten Interaktionen
                     print(f"WARNUNG: Kein Guild-Kontext für ADMIN_MOD_PING_ROLE_ID.")
            except ValueError:
                print(f"WARNUNG: ADMIN_MOD_PING_ROLE_ID ('{admin_mod_ping_role_id_str}') ist keine gültige ID.")
            except Exception as e:
                print(f"FEHLER beim Verarbeiten der ADMIN_MOD_PING_ROLE_ID: {e}")


        try:
            thread_message_content = initial_content_for_thread_creation + mention_text
            
            # Tagging basierend auf 'forum_tag_name' aus der Kategorie-Konfiguration
            applied_tags = []
            target_tag_name = selected_category.get("forum_tag_name")
            if target_tag_name:
                available_tags = appeals_forum.available_tags
                found_tag = discord.utils.find(lambda tag: tag.name == target_tag_name, available_tags)
                if found_tag:
                    applied_tags.append(found_tag)
                    print(f"INFO: Forum-Tag '{target_tag_name}' gefunden und wird für Kategorie '{selected_category['category_id']}' angewendet.")
                else:
                    print(f"WARNUNG: Forum-Tag '{target_tag_name}' (für Kategorie '{selected_category['category_id']}') nicht im Forum '{appeals_forum.name}' (ID: {APPEALS_FORUM_ID}) gefunden.")
            else:
                print(f"INFO: Kein 'forum_tag_name' für Kategorie '{selected_category['category_id']}' definiert.")

            thread = await appeals_forum.create_thread(
                name=thread_title,
                content=thread_message_content, 
                applied_tags=applied_tags if applied_tags else discord.utils.MISSING # type: ignore
            )
            ticket_embed.set_footer(text=f"Ticket ID: {thread.id} | Kategorie: {selected_category['category_id']}")
            
            await thread.send(embed=ticket_embed, view=TicketActionsView(client=self.client_ref)) # type: ignore
            
            tag_info_msg = f" (Tag: {found_tag.name})" if found_tag and target_tag_name else ""
            if not found_tag and target_tag_name: # Tag war definiert, aber nicht gefunden
                tag_info_msg = f" (Hinweis: Der konfigurierte Tag '{target_tag_name}' wurde im Forum nicht gefunden.)"

            # Wichtig: followup verwenden, da die Interaktion vom Modal kommt und gedeffert wurde
            await interaction.followup.send(
                f"Dein Ticket '{ticket_type_name}' wurde erfolgreich erstellt! Du findest es hier: {thread.mention}{tag_info_msg}",
                ephemeral=True
            )
            
            log_action_view_instance = TicketActionsView(client=self.client_ref if self.client_ref else interaction.client) # type: ignore
            log_message_detail = f"Neues Ticket '{ticket_type_name}' (Kategorie: {selected_category['category_id']}) von {user.mention} erstellt im Thread {thread.mention}."
            if found_tag and target_tag_name:
                log_message_detail += f" Tag '{found_tag.name}' angewendet."
            elif target_tag_name: # Tag definiert, aber nicht gefunden
                log_message_detail += f" Konfigurierter Tag '{target_tag_name}' nicht gefunden."
            else: # Kein Tag definiert
                 log_message_detail += " Kein spezifischer Forum-Tag für diese Kategorie konfiguriert."

            await log_action_view_instance.log_ticket_action(interaction, "Ticket Erstellt", log_message_detail, discord.Color.blue(), thread_id=thread.id)

        except discord.Forbidden as fe:
            await interaction.followup.send(f"Fehler beim Erstellen des Tickets: Ich habe möglicherweise nicht die Berechtigung, Threads zu erstellen oder Tags anzuwenden. Bitte überprüfe meine Rollenberechtigungen im Forum. ({fe})", ephemeral=True)
            print(f"FEHLER (Forbidden) beim Erstellen des Tickets oder Anwenden von Tags: {fe}")
        except Exception as e:
            await interaction.followup.send(f"Ein unerwarteter Fehler ist beim Erstellen des Tickets aufgetreten. Bitte versuche es später erneut oder kontaktiere einen Admin. Fehler: {e}",ephemeral=True)
            print(f"FEHLER beim Erstellen des Tickets nach Modal: {e}")
            import traceback
            traceback.print_exc()


# --- Event: Bot ist bereit ---
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
    # Hier könnten zusätzliche Kanalüberprüfungen beim Start stattfinden, z.B. ob die Kanal-IDs gültig sind.
    # Beispiel:
    open_ticket_channel = client.get_channel(OPEN_TICKET_CHANNEL_ID)
    if not open_ticket_channel:
        print(f"WARNUNG: Open a Ticket Channel mit ID {OPEN_TICKET_CHANNEL_ID} wurde nicht gefunden.")
    appeals_forum = client.get_channel(APPEALS_FORUM_ID)
    if not appeals_forum:
        print(f"WARNUNG: Appeals Forum mit ID {APPEALS_FORUM_ID} wurde nicht gefunden.")
    if TICKET_LOG_CHANNEL_ID:
        try:
            log_channel = client.get_channel(int(TICKET_LOG_CHANNEL_ID))
            if not log_channel:
                print(f"WARNUNG: Ticket Log Channel mit ID {TICKET_LOG_CHANNEL_ID} wurde nicht gefunden.")
        except ValueError:
             print(f"WARNUNG: TICKET_LOG_CHANNEL_ID ('{TICKET_LOG_CHANNEL_ID}') ist keine gültige ID.")


# --- Slash-Befehl: Setup Ticket Panel ---
@client.tree.command(name="setup_ticket_panel", description="Postet das Ticket-Panel im 'Open a Ticket'-Kanal.")
@app_commands.checks.has_permissions(administrator=True)
async def setup_ticket_panel_command(interaction: discord.Interaction):
    """
    Sendet das Ticket-Erstellungspanel in den konfigurierten Kanal.
    Dieser Befehl kann nur von Administratoren ausgeführt werden.
    """
    target_channel_id = OPEN_TICKET_CHANNEL_ID
    target_channel = interaction.guild.get_channel(target_channel_id)

    if not target_channel:
        await interaction.response.send_message(
            f"Fehler: Der Kanal zum Öffnen von Tickets (ID: {target_channel_id}) wurde nicht gefunden. "
            "Bitte überprüfe die `OPEN_TICKET_CHANNEL_ID` in deiner `.env`-Datei.",
            ephemeral=True
        )
        return

    if not isinstance(target_channel, discord.TextChannel):
        await interaction.response.send_message(
            f"Fehler: Der konfigurierte Ticket-Kanal (ID: {target_channel_id}) ist kein Textkanal. "
            "Bitte wähle einen Textkanal aus.",
            ephemeral=True
        )
        return

    # Erstelle das Embed für das Ticket-Panel
    panel_embed = Embed(
        title="🌟 Support Ticket Erstellen 🌟",
        description=(
            "Willkommen beim Support-System!\n\n"
            "Klicke auf einen der untenstehenden Buttons, um ein Ticket für dein spezifisches Anliegen zu erstellen. "
            "Ein Teammitglied wird sich so schnell wie möglich um dich kümmern."
        ),
        color=discord.Color.blue() # Du kannst hier jede gewünschte Farbe verwenden
    )
    panel_embed.set_footer(text=f"{interaction.guild.name} Support")
    # Optional: Ein Thumbnail oder Bild hinzufügen
    # panel_embed.set_thumbnail(url="URL_ZU_DEINEM_SERVER_LOGO_ODER_EINEM_PASSENDEN_BILD")

    # Erstelle die View mit den Buttons
    # Stelle sicher, dass die TicketPanelView-Klasse den client korrekt erhält,
    # falls sie ihn für Callbacks benötigt, die nicht direkt über die Interaction laufen.
    # In diesem Fall wird der Client in der `setup_hook` der `TicketBotClient` Klasse
    # bereits an die persistenten Views übergeben.
    panel_view = TicketPanelView(client=client)

    try:
        await target_channel.send(embed=panel_embed, view=panel_view)
        await interaction.response.send_message(
            f"Das Ticket-Panel wurde erfolgreich im Kanal {target_channel.mention} gepostet.",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "Fehler: Ich habe keine Berechtigung, Nachrichten in den angegebenen Ticket-Kanal zu senden. "
            "Bitte überprüfe meine Rollenberechtigungen.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Ein unerwarteter Fehler ist beim Posten des Panels aufgetreten: {e}",
            ephemeral=True
        )
        print(f"Fehler beim Ausführen von setup_ticket_panel_command: {e}")

@setup_ticket_panel_command.error
async def setup_ticket_panel_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Fehler: Du hast nicht die erforderlichen Berechtigungen (Administrator), um diesen Befehl auszuführen.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Ein Fehler ist aufgetreten: {error}", ephemeral=True)
        print(f"Fehler im setup_ticket_panel_command: {error}")

# --- Start des Bots ---
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("FEHLER: DISCORD_TOKEN nicht in .env gefunden.")
    elif not OPEN_TICKET_CHANNEL_ID:
        print("FEHLER: OPEN_TICKET_CHANNEL_ID nicht in .env gefunden oder ist 0.")
    elif not APPEALS_FORUM_ID:
        print("FEHLER: APPEALS_FORUM_ID nicht in .env gefunden oder ist 0.")
    else:
        client.run(DISCORD_TOKEN)
