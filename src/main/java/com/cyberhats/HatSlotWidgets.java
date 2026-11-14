package com.cyberhats;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.AbstractButton;
import net.minecraft.client.gui.components.AbstractWidget;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.narration.NarrationElementOutput;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.client.gui.screens.inventory.CreativeModeInventoryScreen;
import net.minecraft.client.gui.screens.inventory.InventoryScreen;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.player.Player;
import net.minecraftforge.client.event.ScreenEvent;

/**
 * The frame of the Hat slot and the button that shows or hides the hat, on the inventory screen and on the creative
 * inventory's own tab. The game's background has no frame where the slot is, so this draws one, under the slot.
 */
final class HatSlotWidgets {
    private static final ResourceLocation SHOWN = CyberHats.id("textures/gui/hat_shown.png"), HIDDEN = CyberHats.id("textures/gui/hat_hidden.png");

    private HatSlotWidgets() {}

    static void addTo(ScreenEvent.Init.Post event) {
        if (!HatSlot.ownSlot()) {
            return;
        }
        if (event.getScreen() instanceof InventoryScreen screen) {
            event.addListener(new Frame(screen, HatSlot.X, HatSlot.Y));
            event.addListener(new Toggle(screen, HatSlot.X + 4, HatSlot.Y - 11));
        } else if (event.getScreen() instanceof CreativeModeInventoryScreen screen) {
            event.addListener(new Frame(screen, HatSlot.CREATIVE_X, HatSlot.CREATIVE_Y));
            event.addListener(new Toggle(screen, HatSlot.CREATIVE_X + 20, HatSlot.CREATIVE_Y + 4));
        }
    }

    /** Placed against the screen at every frame: the recipe book moves it, and the creative screen changes tabs. */
    private static boolean place(AbstractWidget widget, AbstractContainerScreen<?> screen, int dx, int dy) {
        widget.setX(screen.getGuiLeft() + dx);
        widget.setY(screen.getGuiTop() + dy);
        widget.visible = !(screen instanceof CreativeModeInventoryScreen creative) || creative.isInventoryOpen();
        return widget.visible;
    }

    private static final class Frame extends AbstractWidget {
        private final AbstractContainerScreen<?> screen;
        private final int dx, dy;

        Frame(AbstractContainerScreen<?> screen, int slotX, int slotY) {
            super(0, 0, 18, 18, Component.empty());
            this.screen = screen;
            this.dx = slotX - 1;
            this.dy = slotY - 1;
            // Only drawn: clicks go through to the slot
            this.active = false;
        }

        @Override
        protected void renderWidget(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
            if (!place(this, screen, dx, dy)) {
                return;
            }
            int x = getX(), y = getY();
            // The vanilla slot: dark above and left, white below and right
            graphics.fill(x, y, x + 18, y + 18, 0xFF8B8B8B);
            graphics.fill(x, y, x + 17, y + 1, 0xFF373737);
            graphics.fill(x, y, x + 1, y + 17, 0xFF373737);
            graphics.fill(x + 1, y + 17, x + 18, y + 18, 0xFFFFFFFF);
            graphics.fill(x + 17, y + 1, x + 18, y + 18, 0xFFFFFFFF);
        }

        @Override
        protected void updateWidgetNarration(NarrationElementOutput output) {}
    }

    private static final class Toggle extends AbstractButton {
        private final AbstractContainerScreen<?> screen;
        private final int dx, dy;

        Toggle(AbstractContainerScreen<?> screen, int x, int y) {
            super(0, 0, 9, 9, Component.translatable("cyberhats.hat_slot.toggle"));
            this.screen = screen;
            this.dx = x;
            this.dy = y;
        }

        @Override
        public void onPress() {
            Player player = Minecraft.getInstance().player;
            HatSlot.sendToggle();
            // Shown at once; the server sends the same back
            HatSlot.Worn worn = HatSlot.worn(player);
            HatSlot.setWorn(player, new HatSlot.Worn(worn.hat(), !worn.shown()));
        }

        @Override
        protected void renderWidget(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
            if (!place(this, screen, dx, dy)) {
                return;
            }
            boolean shown = HatSlot.worn(Minecraft.getInstance().player).shown();
            setTooltip(Tooltip.create(Component.translatable(shown ? "cyberhats.hat_slot.hide" : "cyberhats.hat_slot.show")));
            graphics.setColor(1.0F, 1.0F, 1.0F, isHoveredOrFocused() ? 1.0F : 0.8F);
            graphics.blit(shown ? SHOWN : HIDDEN, getX(), getY(), 0, 0, 9, 9, 9, 9);
            graphics.setColor(1.0F, 1.0F, 1.0F, 1.0F);
        }

        @Override
        protected void updateWidgetNarration(NarrationElementOutput output) {
            defaultButtonNarrationText(output);
        }
    }
}
