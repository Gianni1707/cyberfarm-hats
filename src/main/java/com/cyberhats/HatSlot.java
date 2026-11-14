package com.cyberhats;

import java.util.function.Supplier;

import com.mojang.datafixers.util.Pair;

import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.FriendlyByteBuf;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.Container;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.InventoryMenu;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.GameRules;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.entity.living.LivingDropsEvent;
import net.minecraftforge.event.entity.player.PlayerEvent;
import net.minecraftforge.fml.DistExecutor;
import net.minecraftforge.fml.ModList;
import net.minecraftforge.network.NetworkEvent;
import net.minecraftforge.network.NetworkRegistry;
import net.minecraftforge.network.PacketDistributor;
import net.minecraftforge.network.simple.SimpleChannel;
import net.minecraftforge.registries.ForgeRegistries;

/**
 * The cosmetic Hat slot: a hat worn there shows on the player's head in place of the helmet, which still protects.
 * It sits beside the armor in the inventory, with a button to hide the hat. With a mod that has cosmetic slots of its
 * own (Curios, Cosmetic Armor Reworked) there is no Hat slot: the hats go in that mod's slots instead.
 *
 * The slot's contents live in the player's persisted data, which Forge carries over a respawn; the server sends them to
 * whoever sees the player.
 */
public final class HatSlot {
    /** Where the slot sits in the inventory screen: right of the player, above the offhand. */
    public static final int X = 77, Y = 44;
    /** Where it sits on the creative inventory's own tab: right of the armor, where that tab is empty. */
    public static final int CREATIVE_X = 127, CREATIVE_Y = 20;
    public static final String COSMETIC_ARMOR = "cosmeticarmorreworked";
    private static final String KEY = "cyberhats_hat_slot";

    /** What the slot holds, and whether the player chose to show it. */
    public record Worn(ItemStack hat, boolean shown) {
        public static final Worn EMPTY = new Worn(ItemStack.EMPTY, true);
    }

    private static final String VERSION = "1";
    private static final SimpleChannel CHANNEL = NetworkRegistry.newSimpleChannel(CyberHats.id("main"), () -> VERSION, VERSION::equals, VERSION::equals);

    /** Sent by the button beside the slot. */
    record ToggleShown() {}

    /** A player's slot, sent to them and to everyone who sees them. */
    record Sync(int entity, ItemStack hat, boolean shown) {}

    private HatSlot() {}

    static void register() {
        CHANNEL.registerMessage(0, ToggleShown.class, (message, buf) -> {}, buf -> new ToggleShown(), HatSlot::toggle);
        CHANNEL.registerMessage(1, Sync.class, (message, buf) -> {
            buf.writeVarInt(message.entity());
            buf.writeItem(message.hat());
            buf.writeBoolean(message.shown());
        }, buf -> new Sync(buf.readVarInt(), buf.readItem(), buf.readBoolean()), HatSlot::receive);
        MinecraftForge.EVENT_BUS.addListener(HatSlot::dropOnDeath);
        MinecraftForge.EVENT_BUS.addListener((PlayerEvent.PlayerLoggedInEvent event) -> sendToSelf(event.getEntity()));
        MinecraftForge.EVENT_BUS.addListener((PlayerEvent.PlayerRespawnEvent event) -> sendToSelf(event.getEntity()));
        MinecraftForge.EVENT_BUS.addListener((PlayerEvent.PlayerChangedDimensionEvent event) -> sendToSelf(event.getEntity()));
        MinecraftForge.EVENT_BUS.addListener((PlayerEvent.StartTracking event) -> {
            if (event.getTarget() instanceof Player seen && event.getEntity() instanceof ServerPlayer viewer) {
                CHANNEL.send(PacketDistributor.PLAYER.with(() -> viewer), sync(seen));
            }
        });
    }

    /** Whether this game has our own Hat slot: not when another mod brings cosmetic slots. */
    public static boolean ownSlot() {
        return !ModList.get().isLoaded(CuriosHats.MODID) && !ModList.get().isLoaded(COSMETIC_ARMOR);
    }

    public static boolean isHat(ItemStack stack) {
        ResourceLocation id = ForgeRegistries.ITEMS.getKey(stack.getItem());
        return id != null && id.getNamespace().equals(CyberHats.MODID);
    }

    public static Worn worn(Player player) {
        CompoundTag persisted = player.getPersistentData().getCompound(Player.PERSISTED_NBT_TAG);
        if (!persisted.contains(KEY)) {
            return Worn.EMPTY;
        }
        CompoundTag tag = persisted.getCompound(KEY);
        return new Worn(ItemStack.of(tag.getCompound("hat")), !tag.contains("shown") || tag.getBoolean("shown"));
    }

    /** Stores the slot and, on the server, tells the player and those who see them. */
    public static void setWorn(Player player, Worn worn) {
        CompoundTag data = player.getPersistentData();
        CompoundTag persisted = data.getCompound(Player.PERSISTED_NBT_TAG);
        CompoundTag tag = new CompoundTag();
        tag.put("hat", worn.hat().save(new CompoundTag()));
        tag.putBoolean("shown", worn.shown());
        persisted.put(KEY, tag);
        data.put(Player.PERSISTED_NBT_TAG, persisted);
        if (player instanceof ServerPlayer && player.level() instanceof ServerLevel) {
            CHANNEL.send(PacketDistributor.TRACKING_ENTITY_AND_SELF.with(() -> player), sync(player));
        }
    }

    /** The hat to draw on the player's head instead of the helmet, or empty. */
    public static ItemStack shownHat(Player player) {
        Worn worn = worn(player);
        return worn.shown() ? worn.hat() : ItemStack.EMPTY;
    }

    static void sendToggle() {
        CHANNEL.sendToServer(new ToggleShown());
    }

    private static Sync sync(Player player) {
        Worn worn = worn(player);
        return new Sync(player.getId(), worn.hat(), worn.shown());
    }

    private static void sendToSelf(Player player) {
        if (player instanceof ServerPlayer self) {
            CHANNEL.send(PacketDistributor.PLAYER.with(() -> self), sync(player));
        }
    }

    private static void toggle(ToggleShown message, Supplier<NetworkEvent.Context> context) {
        context.get().enqueueWork(() -> {
            ServerPlayer player = context.get().getSender();
            if (player != null) {
                Worn worn = worn(player);
                setWorn(player, new Worn(worn.hat(), !worn.shown()));
            }
        });
        context.get().setPacketHandled(true);
    }

    private static void receive(Sync message, Supplier<NetworkEvent.Context> context) {
        context.get().enqueueWork(() -> DistExecutor.unsafeRunWhenOn(Dist.CLIENT,
                () -> () -> CyberHatsClient.applySync(message.entity(), new Worn(message.hat(), message.shown()))));
        context.get().setPacketHandled(true);
    }

    private static void dropOnDeath(LivingDropsEvent event) {
        if (event.getEntity() instanceof Player player && player.level() instanceof ServerLevel level
                && !level.getGameRules().getBoolean(GameRules.RULE_KEEPINVENTORY)) {
            Worn worn = worn(player);
            if (!worn.hat().isEmpty()) {
                event.getDrops().add(new ItemEntity(level, player.getX(), player.getEyeY() - 0.3, player.getZ(), worn.hat()));
                setWorn(player, new Worn(ItemStack.EMPTY, worn.shown()));
            }
        }
    }

    /** The slot added to the player's inventory menu, on both sides alike (see InventoryMenuMixin). */
    public static Slot slot(Player player) {
        return new Holder(player);
    }

    public static final class Holder extends Slot {
        private static final Pair<ResourceLocation, ResourceLocation> ICON = Pair.of(InventoryMenu.BLOCK_ATLAS, CyberHats.id("item/empty_hat_slot"));

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
        public Pair<ResourceLocation, ResourceLocation> getNoItemIcon() {
            return ICON;
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
            setWorn(player, new Worn(stack, worn(player).shown()));
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
