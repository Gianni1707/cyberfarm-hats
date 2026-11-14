package com.cyberhats;

import com.mojang.serialization.Codec;
import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;

import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.resources.Identifier;
import net.minecraft.network.codec.ByteBufCodecs;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.Container;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.gamerules.GameRules;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.ModList;
import net.neoforged.neoforge.attachment.AttachmentType;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.entity.living.LivingDropsEvent;
import net.neoforged.neoforge.network.event.RegisterPayloadHandlersEvent;
import net.neoforged.neoforge.network.handling.IPayloadContext;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;
import net.neoforged.neoforge.registries.NeoForgeRegistries;

/**
 * The cosmetic Hat slot: a hat worn there shows on the player's head in place of the helmet, which still protects.
 * It sits beside the armor in the inventory, with a button to hide the hat. With a mod that has cosmetic slots of its
 * own (Curios) there is no Hat slot: the hats go in that mod's head slot instead (see {@link CuriosHats}).
 */
public final class HatSlot {
    /** Where the slot sits in the inventory screen: right of the player, above the offhand. */
    public static final int X = 77, Y = 44;
    /** Where it sits on the creative inventory's own tab: right of the armor, where that tab is empty. */
    public static final int CREATIVE_X = 127, CREATIVE_Y = 20;

    /** What the slot holds, and whether the player chose to show it. */
    public record Worn(ItemStack hat, boolean shown) {
        public static final Worn EMPTY = new Worn(ItemStack.EMPTY, true);
        static final MapCodec<Worn> CODEC = RecordCodecBuilder.mapCodec(i -> i.group(
                ItemStack.OPTIONAL_CODEC.optionalFieldOf("hat", ItemStack.EMPTY).forGetter(Worn::hat),
                Codec.BOOL.optionalFieldOf("shown", true).forGetter(Worn::shown)).apply(i, Worn::new));
        static final StreamCodec<RegistryFriendlyByteBuf, Worn> STREAM_CODEC = StreamCodec.composite(
                ItemStack.OPTIONAL_STREAM_CODEC, Worn::hat, ByteBufCodecs.BOOL, Worn::shown, Worn::new);
    }

    private static final DeferredRegister<AttachmentType<?>> ATTACHMENTS = DeferredRegister.create(NeoForgeRegistries.ATTACHMENT_TYPES, CyberHats.MODID);
    /** Saved with the player, kept through death with keepInventory (dropped otherwise), sent to everyone who sees them. */
    public static final DeferredHolder<AttachmentType<?>, AttachmentType<Worn>> WORN = ATTACHMENTS.register("hat_slot",
            () -> AttachmentType.builder(() -> Worn.EMPTY).serialize(Worn.CODEC).copyOnDeath().sync(Worn.STREAM_CODEC).build());

    /** Sent by the button beside the slot. */
    public record ToggleShown() implements CustomPacketPayload {
        public static final Type<ToggleShown> TYPE = new Type<>(CyberHats.id("toggle_hat"));
        static final StreamCodec<RegistryFriendlyByteBuf, ToggleShown> STREAM_CODEC = StreamCodec.unit(new ToggleShown());

        @Override
        public Type<ToggleShown> type() {
            return TYPE;
        }
    }

    private HatSlot() {}

    static void register(IEventBus modBus) {
        ATTACHMENTS.register(modBus);
        modBus.addListener((RegisterPayloadHandlersEvent event) ->
                event.registrar("1").playToServer(ToggleShown.TYPE, ToggleShown.STREAM_CODEC, HatSlot::toggle));
        NeoForge.EVENT_BUS.addListener(HatSlot::dropOnDeath);
    }

    /** Whether this game has our own Hat slot: not when another mod brings cosmetic slots. */
    public static boolean ownSlot() {
        return !ModList.get().isLoaded(CuriosHats.MODID);
    }

    public static boolean isHat(ItemStack stack) {
        return BuiltInRegistries.ITEM.getKey(stack.getItem()).getNamespace().equals(CyberHats.MODID);
    }

    public static Worn worn(Player player) {
        return player.getData(WORN);
    }

    /** The hat to draw on the player's head instead of the helmet, or empty. */
    public static ItemStack shownHat(Player player) {
        Worn worn = worn(player);
        return worn.shown() ? worn.hat() : ItemStack.EMPTY;
    }

    private static void toggle(ToggleShown payload, IPayloadContext context) {
        Player player = context.player();
        Worn worn = worn(player);
        player.setData(WORN, new Worn(worn.hat(), !worn.shown()));
    }

    private static void dropOnDeath(LivingDropsEvent event) {
        if (event.getEntity() instanceof Player player && player.level() instanceof ServerLevel level
                && !level.getGameRules().get(GameRules.KEEP_INVENTORY)) {
            Worn worn = worn(player);
            if (!worn.hat().isEmpty()) {
                event.getDrops().add(new ItemEntity(level, player.getX(), player.getEyeY() - 0.3, player.getZ(), worn.hat()));
                player.setData(WORN, new Worn(ItemStack.EMPTY, worn.shown()));
            }
        }
    }

    /** The slot added to the player's inventory menu, on both sides alike (see InventoryMenuMixin). */
    public static Slot slot(Player player) {
        return new Holder(player);
    }

    public static final class Holder extends Slot {
        private Holder(Player player) {
            super(new OneHat(player), 0, X, Y);
        }

        @Override
        public boolean mayPlace(ItemStack stack) {
            return isHat(stack);
        }

        @Override
        public int getMaxStackSize() {
            return 1;
        }

        @Override
        public Identifier getNoItemIcon() {
            return CyberHats.id("container/slot/hat");
        }
    }

    /** The player's Hat slot seen as a one-item container. */
    private record OneHat(Player player) implements Container {
        @Override
        public int getContainerSize() {
            return 1;
        }

        @Override
        public boolean isEmpty() {
            return getItem(0).isEmpty();
        }

        @Override
        public ItemStack getItem(int slot) {
            return worn(player).hat();
        }

        @Override
        public ItemStack removeItem(int slot, int count) {
            ItemStack hat = getItem(0);
            if (hat.isEmpty() || count <= 0) {
                return ItemStack.EMPTY;
            }
            setItem(0, ItemStack.EMPTY);
            return hat;
        }

        @Override
        public ItemStack removeItemNoUpdate(int slot) {
            return removeItem(slot, 1);
        }

        @Override
        public void setItem(int slot, ItemStack stack) {
            player.setData(WORN, new Worn(stack, worn(player).shown()));
        }

        @Override
        public void setChanged() {}

        @Override
        public boolean stillValid(Player user) {
            return user == player;
        }

        @Override
        public void clearContent() {
            setItem(0, ItemStack.EMPTY);
        }
    }
}
