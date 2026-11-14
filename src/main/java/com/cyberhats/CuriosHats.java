package com.cyberhats;

import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.item.ItemStack;
import top.theillusivec4.curios.api.CuriosApi;
import top.theillusivec4.curios.api.type.inventory.ICurioStacksHandler;

/**
 * With Curios installed, hats go in its head slot (the tag data/curios/tags/item/head.json lets them in, and
 * data/cyberhats/curios/entities/hats.json gives players that slot). Only touched when Curios is loaded.
 */
public final class CuriosHats {
    public static final String MODID = "curios";

    private CuriosHats() {}

    /** The hat to draw on the head in place of the helmet: the cosmetic one first, then a worn one Curios shows. */
    public static ItemStack shownHat(LivingEntity entity) {
        return CuriosApi.getCuriosInventory(entity).flatMap(curios -> curios.getStacksHandler("head"))
                .map(CuriosHats::shownHat).orElse(ItemStack.EMPTY);
    }

    private static ItemStack shownHat(ICurioStacksHandler head) {
        for (int i = 0; i < head.getSlots(); i++) {
            ItemStack cosmetic = head.hasCosmetic() ? head.getCosmeticStacks().getStackInSlot(i) : ItemStack.EMPTY;
            if (HatSlot.isHat(cosmetic)) {
                return cosmetic;
            }
            ItemStack worn = head.getStacks().getStackInSlot(i);
            if (HatSlot.isHat(worn) && head.getRenders().get(i)) {
                return worn;
            }
        }
        return ItemStack.EMPTY;
    }
}
